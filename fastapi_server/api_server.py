#!/usr/bin/env python3
"""
FastAPI server for D-Helix binary verification
Accepts binary + decompiled code, returns Z3 verification results

Fixed to match generate_symbolic.py behavior exactly.
"""

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
import sys
import tempfile
import shutil
import subprocess
import signal
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import uuid
import logging
import re
from contextlib import asynccontextmanager

# Add D-helix module path
DHELIX_ANGR_PATH = "/root/work/D-helix-fixed/D-helix/D_helix_angr"
sys.path.insert(0, DHELIX_ANGR_PATH)

# Change to D-helix directory for relative path compatibility
os.chdir(DHELIX_ANGR_PATH)

# Import D-helix modules
import angr
import claripy
from claripy.backends.backend_smtlib_solvers import *
import convert
import analyze_angr

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
TEMP_BASE_DIR = "/tmp/dhelix_api"
COMPILER = "/root/llvm-3.8/bin/clang"
KLEE_BIN = "/root/PROMPT/build/bin/klee"
Z3_BIN = "/root/z3/bin/z3"
TIMEOUT_KLEE = 30
TIMEOUT_Z3 = 30
MAX_WORKERS = 4


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cleanup temp directories on startup/shutdown"""
    if os.path.exists(TEMP_BASE_DIR):
        shutil.rmtree(TEMP_BASE_DIR, ignore_errors=True)
    os.makedirs(TEMP_BASE_DIR, exist_ok=True)
    logger.info(f"D-Helix API Server started, temp dir: {TEMP_BASE_DIR}")
    
    yield
    
    if os.path.exists(TEMP_BASE_DIR):
        shutil.rmtree(TEMP_BASE_DIR, ignore_errors=True)
    logger.info("D-Helix API Server shutdown")


app = FastAPI(
    title="D-Helix Verification API",
    description="Binary decompilation verification using symbolic execution",
    version="1.0.0",
    lifespan=lifespan
)


class VerificationResult(BaseModel):
    """Response model for verification results"""
    request_id: str
    status: str  # "success", "error"
    z3_formula: Optional[str] = None
    result: Optional[str] = None  # "sat" or "unsat"
    counterexample: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


def pkiller():
    """Kill child processes when parent dies"""
    from ctypes import cdll
    cdll['libc.so.6'].prctl(1, 9)


def run_cmd_with_timeout(cmd: str, timeout: int) -> Tuple[int, str, str]:
    """Run command with timeout, return (exit_code, stdout, stderr)"""
    try:
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            start_new_session=True,
            preexec_fn=pkiller
        )
        
        stdout, stderr = process.communicate(timeout=timeout)
        return process.returncode, stdout.decode('utf-8', errors='ignore'), stderr.decode('utf-8', errors='ignore')
    
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        return -1, "", f"Timeout after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def preprocess_decompiled_code(code: str, function_name: str) -> str:
    """
    Preprocess decompiled C code like generate_symbolic.py does:
    - Add includes
    - Add typedefs
    - Add main function stub if not main
    """
    preprocessed = """#include <stdio.h>
#include <stdbool.h>
#include <stdint.h>
typedef unsigned int    BOT;
typedef unsigned int    uint;
typedef unsigned long   ulong;

"""
    preprocessed += code
    
    # Add main stub if function is not main
    if "main" not in function_name[0:4]:
        preprocessed += "\n\nint main(int param_1, const char *param_2[]){}\n"
    
    return preprocessed


def compile_to_bitcode(decompiled_c_path: str, output_bc_path: str, log_path: str) -> bool:
    """
    Compile decompiled C code to LLVM bitcode with automatic error recovery
    like automatic_compilation() in generate_symbolic.py
    """
    max_iterations = 3
    
    for iteration in range(max_iterations):
        cmd = f"{COMPILER} -emit-llvm -O0 -c -Wno-everything {decompiled_c_path} -o {output_bc_path} 2> {log_path}"
        exit_code, stdout, stderr = run_cmd_with_timeout(cmd, 10)
        
        # Check if compilation succeeded
        if os.path.exists(output_bc_path):
            return True
        
        # Read error log
        if not os.path.exists(log_path):
            continue
            
        with open(log_path, 'r') as f:
            log_lines = f.readlines()
        
        if not log_lines:
            continue
        
        # Find undeclared identifiers and add them
        declare_global_list = []
        for line in log_lines:
            if 'use of undeclared identifier' in line:
                match = re.search(r"use of undeclared identifier '(.+?)'", line)
                if match:
                    declare_global_list.append(match.group(1))
        
        declare_global_list = list(set(declare_global_list))
        
        if not declare_global_list:
            break
        
        # Read current file and add declarations
        with open(decompiled_c_path, 'r') as f:
            content_lines = f.readlines()
        
        with open(decompiled_c_path, 'w') as f:
            # Write first 6 lines (headers and typedefs)
            for i in range(min(6, len(content_lines))):
                f.write(content_lines[i])
            
            # Add global variable declarations
            for var in declare_global_list:
                f.write(f"int {var}; //add global variable\n")
            
            # Write rest of file
            for i in range(6, len(content_lines)):
                f.write(content_lines[i])
        
        logger.info(f"Added {len(declare_global_list)} undeclared variables, retrying compilation...")
    
    return os.path.exists(output_bc_path)


def run_klee_symbolic_execution(
    bc_path: str,
    function_name: str,
    model_path: str,
    klee_log_path: str,
    klee_error_path: str
) -> Tuple[bool, str]:
    """
    Run KLEE symbolic execution on bitcode.
    KLEE (PROMPT version) uses regex "generatedbc/(.+*?)\\.bc" to extract name.
    It creates /tmp/klee_<extracted_name>_test.txt
    Returns (success, klee_test_file_path).
    """
    try:
        # Create PROMPT model file (matching generate_symbolic.py format)
        with open(model_path, 'w') as f:
            f.write(f"global settings:\ndata models:\nfunction models:\nlifecycle model:\n    entry-point {function_name.replace('.', '_')}")
        
        # KLEE PROMPT uses regex "generatedbc/(.+*?)\\.bc" to extract the name
        # So if bc_path is "/tmp/work/generatedbc/test_add.bc", name is "test_add"
        # The test file path is /tmp/klee_<name>_test.txt
        match = re.search(r'generatedbc/(.+?)\.bc$', bc_path)
        if match:
            klee_name = match.group(1)
        else:
            # Fallback to basename if not in generatedbc directory
            klee_name = os.path.basename(bc_path).replace('.bc', '')
            logger.warning(f"BC path not in generatedbc dir, using basename: {klee_name}")
        
        klee_test_path = f"/tmp/klee_{klee_name}_test.txt"
        
        # Remove old test file if exists
        if os.path.exists(klee_test_path):
            os.remove(klee_test_path)
        
        # Run KLEE - stdout goes to klee_log_path, stderr to error path
        # But the important _test.txt file is created by KLEE internally
        cmd = (
            f"{KLEE_BIN} -prose-api-model={model_path} "
            f"--search=bfs --solver-backend=z3 --posix-runtime {bc_path} "
            f"1> {klee_log_path} 2> {klee_error_path}"
        )
        
        logger.info(f"Running KLEE: {cmd}")
        logger.info(f"Expected KLEE test output: {klee_test_path}")
        exit_code, stdout, stderr = run_cmd_with_timeout(cmd, TIMEOUT_KLEE)
        
        # Check if KLEE completed by looking at error log for 'KLEE: done:'
        klee_success = False
        if os.path.exists(klee_error_path):
            with open(klee_error_path, 'r') as f:
                error_content = f.read()
                if 'KLEE: done:' in error_content:
                    klee_success = True
                    logger.info("KLEE completed successfully")
                else:
                    logger.warning(f"KLEE did not complete. Error log tail: {error_content[-300:]}")
        
        # Verify the test file was created
        if os.path.exists(klee_test_path):
            logger.info(f"KLEE test file created: {klee_test_path}")
        else:
            logger.warning(f"KLEE test file NOT found: {klee_test_path}")
            klee_success = False
        
        return klee_success, klee_test_path
    
    except Exception as e:
        logger.error(f"KLEE execution exception: {e}")
        return False, ""


def run_angr_symbolic_execution(
    binary_path: str,
    function_name: str,
    angr_log_path: str,
    function_args_string: str = ""
) -> bool:
    """
    Run Angr symbolic execution on binary.
    Matches generate_symbolic.py main_each_function_angr() exactly.
    """
    try:
        # Update muqi global variables for this request
        from angr import muqi
        muqi.programe_function_name_txt = angr_log_path
        muqi.decompiler_read_txt = angr_log_path.replace(".txt", "_gate.txt")
        logger.info(f"Set muqi globals: {muqi.programe_function_name_txt}")
        
        # Load binary
        project = angr.Project(binary_path, auto_load_libs=False, load_debug_info=True)
        
        # Generate CFG
        pcfg = project.analyses.CFGFast(normalize=True, data_references=True)
        
        # Run CompleteCallingConventionsAnalysis (optional, can fail)
        try:
            project.analyses[angr.analyses.CompleteCallingConventionsAnalysis].prep()(
                recover_variables=True, analyze_callsites=True
            )
        except Exception as e:
            logger.warning(f"CompleteCallingConventionsAnalysis failed: {e}")
        
        # Find function address
        required_address = 0
        try:
            required_address = project.loader.find_symbol(function_name).rebased_addr
        except:
            pass
        
        # Try FUN_ prefix parsing
        if "FUN_" in function_name and required_address == 0:
            required_address = int(re.search(r"FUN_(.+?)_", function_name + "_").group(1), 16)
        
        # Try sub_ prefix parsing  
        if "sub_" in function_name and required_address == 0:
            required_address = int(re.search(r"sub_(.+?)_", function_name + "_").group(1), 16)
        
        if required_address == 0:
            logger.error(f"Could not find function address for {function_name}")
            return False
        
        logger.info(f"Found function {function_name} at {hex(required_address)}")
        
        # Get function's transition graph
        try:
            func_cfg = pcfg.functions.get(required_address).transition_graph
        except:
            func_cfg = pcfg
        
        # Write CFG to log file (matching generate_symbolic.py format)
        with open(angr_log_path, 'w') as f:
            f.write(f'Filename: {binary_path}\n')
            f.write(f'Function: {function_name}\n')
            for node in func_cfg.nodes():
                f.write(f"BasicBlock_cfg:[{hex(node.addr)} -> {hex(node.addr + node.size)}]\n")
        
        # Setup symbolic arguments (matching generate_symbolic.py)
        args = []
        for i in range(20):
            args.append(claripy.BVS(f'angr_arg{i}', 8*8))
        
        # Handle pointer arguments if we have function signature
        if function_args_string:
            function_args_list = function_args_string.split(",")
            for i in range(len(function_args_list)):
                if "*" in function_args_list[i]:
                    args[i] = claripy.BVS(f'angr_arg{i}', 256*8)
                    args[i] = angr.PointerWrapper(args[i], buffer=True)
                    logger.info(f"Arg {i} is a pointer")
        
        # Create call state (matching generate_symbolic.py exactly)
        state = project.factory.call_state(
            angr_log_path,  # First arg is log path
            required_address,
            args[0], args[1], args[2], args[3], args[4],
            args[5], args[6], args[7], args[8], args[9], args[10],
            add_options={
                angr.options.CALLLESS,
                angr.options.STRINGS_ANALYSIS,
                angr.options.ZERO_FILL_UNCONSTRAINED_MEMORY,
                angr.options.ZERO_FILL_UNCONSTRAINED_REGISTERS
            },
            remove_options=angr.options.simplification
        )
        
        # Create simulation manager
        sm = project.factory.simulation_manager(state)
        
        # Setup jumpout edges (matching generate_symbolic.py)
        for func in project.kb.functions:
            func_name_iter = pcfg.functions.get(func).name
            if func_name_iter == function_name:
                sm.input_jumpout_edge(list(pcfg._get_jumpout_targets(pcfg.functions.get(func))))
        
        # Setup abort addresses
        abort_address = []
        for func in project.kb.functions:
            func_name_iter = pcfg.functions.get(func).name
            if func_name_iter == "abort":
                abort_address.append(pcfg.functions.get(func).addr)
        sm.input_abort_edge(abort_address)
        
        # Run symbolic execution
        logger.info(f"Running Angr on function {function_name}")
        sm.run()
        logger.info("Angr execution completed")
        
        return True
    
    except Exception as e:
        logger.error(f"Angr execution exception: {e}", exc_info=True)
        return False


def process_klee_output(klee_test_path: str, function_name: str, work_dir: str) -> Tuple[bool, str]:
    """
    Process KLEE output to generate CFG and IR files.
    klee_test_path is the _test.txt file created by KLEE internally.
    Returns (success, klee_cfg_path).
    """
    try:
        # Output files in work_dir
        klee_symbolic_path = os.path.join(work_dir, "klee_symbolic_execution.txt")
        klee_cfg_path = os.path.join(work_dir, "klee_cfg.txt")
        
        # Check if KLEE output exists
        if not os.path.exists(klee_test_path):
            logger.error(f"KLEE test file not found: {klee_test_path}")
            return False, ""
        
        # Check if file has content
        with open(klee_test_path, 'r') as f:
            content = f.read()
            if not content.strip():
                logger.error(f"KLEE test file is empty: {klee_test_path}")
                return False, ""
        
        logger.info(f"KLEE test file size: {len(content)} bytes")
        
        # Import analyze_results functions
        from analyze_results import filter_instruction_in_function, output_cfg_lifter
        
        # Filter KLEE output for the function
        function_list = [function_name]
        exclude_function_list = ["__user_main", "__uClibc_main"]
        
        logger.info(f"Filtering KLEE instructions for {function_name}")
        filter_instruction_in_function(klee_test_path, klee_symbolic_path, function_list, exclude_function_list)
        
        # Check symbolic execution output
        if os.path.exists(klee_symbolic_path):
            with open(klee_symbolic_path, 'r') as f:
                sym_content = f.read()
                logger.info(f"Symbolic execution output size: {len(sym_content)} bytes")
        
        # Generate CFG from KLEE output
        logger.info("Generating KLEE CFG...")
        output_cfg_lifter(function_name, klee_symbolic_path, klee_cfg_path)
        
        # Validate CFG was created and has content
        if not os.path.exists(klee_cfg_path):
            logger.error(f"KLEE CFG not created: {klee_cfg_path}")
            return False, ""
        
        with open(klee_cfg_path, 'r') as f:
            cfg_content = f.read()
            if not cfg_content.strip():
                logger.error(f"KLEE CFG is empty: {klee_cfg_path}")
                return False, ""
        
        logger.info(f"KLEE CFG generated: {len(cfg_content)} bytes")
        return True, klee_cfg_path
    
    except Exception as e:
        logger.error(f"KLEE processing exception: {e}", exc_info=True)
        return False, ""


def generate_z3_formula(
    angr_log_path: str,
    klee_cfg_path: str,
    function_name: str,
    z3_output_path: str
) -> Tuple[bool, bool]:
    """
    Generate Z3 formula from angr and KLEE logs.
    klee_cfg_path is the CFG file from process_klee_output.
    Returns (success, is_unsat).
    """
    try:
        # KLEE paths - derive from cfg path
        klee_cfg_reorder_path = klee_cfg_path.replace("_cfg.txt", "_cfg_decompiler_reorder.txt")
        klee_ir_path = klee_cfg_path.replace("_cfg.txt", "_ir_decompiler.txt")
        
        # Angr IR paths
        angr_ir_first = f"{angr_log_path}_ir_first.txt"
        angr_ir_second = f"{angr_log_path}_ir_second.txt"
        angr_ir_third = f"{angr_log_path}_ir_third.txt"
        angr_ir_third_flip = f"{angr_log_path}_ir_third_flip.txt"
        
        # Convert KLEE CFG to IR
        logger.info("Converting KLEE CFG to IR...")
        convert.cfg_to_ir(klee_cfg_path, klee_cfg_reorder_path, klee_ir_path, True)
        convert.ir_reorder(klee_ir_path)
        
        # Process Angr logs
        logger.info("Processing Angr logs...")
        analyze_angr.reset_global(angr_log_path, angr_ir_first, angr_ir_second, angr_ir_third, angr_ir_third_flip)
        analyze_angr.build_basic_block(angr_log_path, angr_ir_first, angr_ir_second, angr_ir_third, angr_ir_third_flip)
        analyze_angr.generate_ir_first_version(angr_log_path, angr_ir_first, angr_ir_second, angr_ir_third, angr_ir_third_flip)
        analyze_angr.generate_father_block_second_version(angr_log_path, angr_ir_first, angr_ir_second, angr_ir_third, angr_ir_third_flip)
        analyze_angr.generate_children_block_second_version(angr_log_path, angr_ir_first, angr_ir_second, angr_ir_third, angr_ir_third_flip)
        analyze_angr.cfg_to_ir(angr_ir_third, angr_ir_third_flip)
        analyze_angr.ir_reorder(angr_ir_third_flip)
        
        # Generate Z3 formula
        logger.info("Generating Z3 formula...")
        is_unsat = convert.ir_to_z3(angr_log_path, angr_ir_third_flip, klee_ir_path, z3_output_path)
        
        return True, is_unsat
    
    except Exception as e:
        logger.error(f"Z3 formula generation exception: {e}", exc_info=True)
        return False, False


def run_z3_solver(z3_formula_path: str) -> Tuple[Optional[str], Optional[str]]:
    """Run Z3 solver on formula, returns (result, output)"""
    try:
        cmd = f"{Z3_BIN} {z3_formula_path}"
        exit_code, stdout, stderr = run_cmd_with_timeout(cmd, TIMEOUT_Z3)
        
        if exit_code == 0:
            result = stdout.strip().split('\n')[0].strip()
            if result in ['sat', 'unsat']:
                return result, stdout
        
        return None, stdout
    
    except Exception as e:
        logger.error(f"Z3 execution exception: {e}")
        return None, str(e)


def extract_counterexample(z3_formula_path: str) -> Optional[Dict[str, Any]]:
    """Extract counterexample model from Z3 if sat"""
    try:
        with open(z3_formula_path, 'r') as f:
            formula_content = f.read()
        
        process = subprocess.Popen(
            [Z3_BIN, '-in'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        stdout, stderr = process.communicate(
            input=(formula_content + "\n(get-model)").encode(),
            timeout=TIMEOUT_Z3
        )
        
        output = stdout.decode('utf-8', errors='ignore')
        
        model = {}
        lines = output.split('\n')
        for i, line in enumerate(lines):
            if 'define-fun' in line:
                if i + 1 < len(lines):
                    model[line.strip()] = lines[i + 1].strip()
        
        return model if model else None
    
    except Exception as e:
        logger.error(f"Counterexample extraction exception: {e}")
        return None


@app.post("/verify", response_model=VerificationResult)
async def verify_binary(
    binary: UploadFile = File(..., description="Binary file to verify"),
    decompiled_code: UploadFile = File(..., description="Decompiled C source code"),
    function_name: str = Form(..., description="Name of the function to verify")
):
    """
    Verify semantic equivalence between binary and decompiled code.
    """
    request_id = str(uuid.uuid4())
    work_dir = os.path.join(TEMP_BASE_DIR, request_id)
    
    # Use short names for temp files
    short_name = f"req_{request_id[:8]}"
    
    try:
        os.makedirs(work_dir, exist_ok=True)
        logger.info(f"Processing request {request_id}, function: {function_name}")
        
        # Save uploaded files
        binary_path = os.path.join(work_dir, short_name)
        decompiled_path = os.path.join(work_dir, f"{short_name}_{function_name}.c")
        
        with open(binary_path, 'wb') as f:
            f.write(await binary.read())
        
        # Preprocess decompiled code
        raw_code = (await decompiled_code.read()).decode('utf-8', errors='ignore')
        processed_code = preprocess_decompiled_code(raw_code, function_name)
        
        with open(decompiled_path, 'w') as f:
            f.write(processed_code)
        
        os.chmod(binary_path, 0o755)
        
        # Step 1: Compile decompiled code to bitcode
        # IMPORTANT: KLEE PROMPT expects bc files in a 'generatedbc' directory
        # The regex in KLEE is: "generatedbc/(.+*?)\\.bc"
        logger.info(f"[{request_id}] Compiling to bitcode...")
        generatedbc_dir = os.path.join(work_dir, "generatedbc")
        os.makedirs(generatedbc_dir, exist_ok=True)
        bc_path = os.path.join(generatedbc_dir, f"{short_name}_{function_name}.bc")
        compile_log_path = os.path.join(work_dir, f"{short_name}_{function_name}_compile.log")
        
        if not compile_to_bitcode(decompiled_path, bc_path, compile_log_path):
            raise HTTPException(status_code=400, detail="Failed to compile decompiled code")
        
        # Step 2: Run KLEE symbolic execution
        logger.info(f"[{request_id}] Running KLEE...")
        model_path = os.path.join(work_dir, f"model{short_name}_{function_name}.txt")
        # KLEE log is the main output file
        klee_log_path = os.path.join(work_dir, f"klee_{short_name}_{function_name}.txt")
        klee_error_path = os.path.join(work_dir, f"klee_{short_name}_{function_name}_error.txt")
        
        klee_success, klee_test_path = run_klee_symbolic_execution(
            bc_path, function_name, model_path, klee_log_path, klee_error_path
        )
        
        if not klee_success:
            logger.warning(f"[{request_id}] KLEE did not complete successfully")
        
        # Process KLEE output to generate CFG - use the _test.txt file path
        klee_process_success, klee_cfg_path = process_klee_output(klee_test_path, function_name, work_dir)
        if not klee_process_success:
            raise HTTPException(status_code=500, detail="KLEE output processing failed - no valid CFG generated")
        
        # Step 3: Run Angr symbolic execution
        logger.info(f"[{request_id}] Running Angr...")
        angr_log_path = os.path.join(work_dir, f"angr_{short_name}_{function_name}.txt")
        
        angr_success = run_angr_symbolic_execution(
            binary_path, function_name, angr_log_path
        )
        
        if not angr_success:
            raise HTTPException(status_code=500, detail="Angr symbolic execution failed")
        
        # Step 4: Generate Z3 formula - pass the CFG path from process_klee_output
        logger.info(f"[{request_id}] Generating Z3 formula...")
        z3_path = os.path.join(work_dir, f"{short_name}_{function_name}_z3")
        
        z3_success, is_unsat = generate_z3_formula(
            angr_log_path, klee_cfg_path, function_name, z3_path
        )
        
        if not z3_success:
            raise HTTPException(status_code=500, detail="Z3 formula generation failed")
        
        # Adjust Z3 path if unsat
        if is_unsat:
            z3_path = z3_path + "_unsat"
        
        # Read Z3 formula
        with open(z3_path, 'r') as f:
            z3_formula = f.read()
        
        # Step 5: Run Z3 solver
        logger.info(f"[{request_id}] Running Z3 solver...")
        z3_result, z3_output = run_z3_solver(z3_path)
        
        if z3_result is None:
            raise HTTPException(status_code=500, detail="Z3 solver execution failed")
        
        # Step 6: Extract counterexample if sat
        counterexample = None
        if z3_result == "sat":
            logger.info(f"[{request_id}] Extracting counterexample...")
            counterexample = extract_counterexample(z3_path)
        
        logger.info(f"[{request_id}] Verification complete: {z3_result}")
        
        return VerificationResult(
            request_id=request_id,
            status="success",
            z3_formula=z3_formula,
            result=z3_result,
            counterexample=counterexample
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Error: {e}", exc_info=True)
        return VerificationResult(
            request_id=request_id,
            status="error",
            error_message=str(e)
        )
    finally:
        # Cleanup work directory
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except:
            pass


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "D-Helix Verification API",
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    """API information"""
    return {
        "service": "D-Helix Binary Verification API",
        "version": "1.0.0",
        "endpoints": {
            "/verify": "POST - Verify binary against decompiled code",
            "/health": "GET - Health check",
            "/docs": "GET - API documentation"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10012, workers=1)
