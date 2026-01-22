import os
import sys
import math
import time
from time import sleep
import numpy as np
import re

file_name_lifter = "./muqi_cfg_lifter.txt"
file_reorder_lifter = "./muqi_cfg_lifter_reorder.txt"
file_ir_lifter = "./muqi_ir_lifter.txt"

file_name_decompiler = "./muqi_cfg_decompiler.txt"
file_reorder_decompiler = "./muqi_cfg_decompiler_reorder.txt"
file_ir_decompiler = "./muqi_ir_decompiler.txt"

file_z3 = "./muqi_z3"


#subfunction to return different BB being bounded
def return_BB(linelist,islifter,i):
    result = []
    BB_start = -1
    BB_end = -1
    if (islifter) :
        for k in range(len(linelist) -1 - i) :
            if 'BB:[' in linelist[i+k] :
                #print(i+k)
                BB_start = i + k
                BB_end = i + k + 1
                break
    else :
        for k in range(len(linelist) -1 - i) :
            if 'BB_decompile:[' in linelist[i+k] :
                #print(i+k)
                BB_start = i + k
                BB_end = i + k + 3
                break

    result.append(BB_start)
    result.append(BB_end)
    return result

#rewrite finput for the truestatement as followed:
#1. Once find 'Add constraint for trueStatement' 
#   Read until:
#    BB:[_a->_b] 
#    BB:[_a->_c] appears    
#   move these two lines above the 'Add constraint for trueStatement' 
def rewrite_add_constraint(finput,foutput,islifter):
    fin = open(finput,'r')
    linelist = fin.readlines()
    fin.close()

    frewrite = open(foutput,'w')
    #print(foutput)
    i = 0
    while i < len(linelist) -1 :
        func_start = 'Function start' in linelist[i]
        add_const = 'Add constraint for trueStatement' in linelist[i+1]
        add_dirct_const = 'Add direct constraint for trueStatement' in linelist[i+1] or 'Add direct constraint for falseStatement' in linelist[i+1]
        
        dump_start = i + 3
        dump_end = i + 3
        BB_start = -1
        BB_end = -1
        if add_const and func_start :
            for j in range(len(linelist) -1 - i) :
                if '----dump z3 end----' in linelist[i+j] :
                    dump_end = i+j+1
                    break
            result = return_BB(linelist,islifter,i)
            BB_start = result[0]
            BB_end = result[1]
            frewrite.write("\n")
            for k in range(BB_start,BB_end+1):
                frewrite.write(linelist[k])
            frewrite.write("\n")
            frewrite.write(linelist[i])
            frewrite.write(linelist[i+1])
            frewrite.write(linelist[i+2])            
            for k in range(dump_start,dump_end+1) :
                frewrite.write(linelist[k])
            
            i = BB_end + 1
            #print(i)
        elif add_dirct_const and func_start:
            for j in range(len(linelist) -1 - i) :
                if '----dump z3 end----' in linelist[i+j] :
                    dump_end = i+j+1
                    break
            result = return_BB(linelist,islifter,i)
            BB_start = result[0]
            if islifter :
                BB_end = BB_start     #here is a bit tricky. For the direct branch, it takes only one line to the up. Since, in klee, after fork(), either branches.first or branches.second will be run.
            else :
                BB_end = BB_start +1 
            frewrite.write("\n")
            for k in range(BB_start,BB_end+1):
                frewrite.write(linelist[k])
            frewrite.write("\n")
            frewrite.write(linelist[i])
            frewrite.write(linelist[i+1])
            frewrite.write(linelist[i+2])            
            for k in range(dump_start,dump_end+1) :
                frewrite.write(linelist[k])
            
            i = BB_end + 1
        else :
            #print(i)
            #print(linelist[i])
            frewrite.write(linelist[i])
            i += 1
    #print(i)
    frewrite.write(linelist[len(linelist)-1])
    frewrite.close()



def add_block_info(finput,islifter) :
    fin = open(finput,'r')
    linelist = fin.readlines()
    fin.close()

    fout = open(finput,'w')
    i = 0
    BB_start = 0
    BB_end = 0
    
    Block_info_prev_lists = []    # this lists will contains all Block_info from previous nodes it will look like:
                    # = [[0,1,1,2,3],
                    #     [0,1,1,2,4]]
                    #It will follow FIFO for the ite, we just need to 
    
    while i < len(linelist) -1 :
        func_start = 'Function start' in linelist[i]
        add_ite = 'Add constraint for trueStatement' in linelist[i+1]    
        add_ret = 'Inside Ret state.pc ++' in linelist[i+1]
        if func_start:
            
            BB_end = i
            #trace back the BB it expolred,
            k = 0
            while k < i :
                if '----dump z3 end----' in linelist[i-k] :
                    BB_start = i-k+1
                    break
                k += 1
            #because for the first appearance of BB:[a->b], we need to record both block
            Block_info_this_seg = [] #this will be used to record the block list inside this node
            for j in range(BB_start,BB_end) :
                if islifter :
                    if 'BB:[' in linelist[j] :
                        block_a = int(re.search('BB:\[(.+?)->(.+?)\]',linelist[j]).group(1))
                        block_b = int(re.search("BB:\[(.+?)->(.+?)\]",linelist[j]).group(2))
                        Block_info_this_seg.append(block_a)
                        Block_info_this_seg.append(block_b)
                else :
                    if 'BB_decompile:[' in linelist[j] :
                        block_a = int(re.search('BB_decompile:\[(.+?)->(.+?)\]',linelist[j]).group(1))
                        block_b = int(re.search("BB_decompile:\[(.+?)->(.+?)\]",linelist[j]).group(2))
                        Block_info_this_seg.append(block_a)
                        Block_info_this_seg.append(block_b)
            
            Start_block_index = Block_info_this_seg[0]
            '''
            if Block_info_this_seg:
                Start_block_index = Block_info_this_seg[0]
            else :
                Start_block_index = 0
                Block_info_this_seg.append(0)
                Block_info_this_seg.append(0)
            '''            
            #find the father node
            First_found = True
            Block_info= [] # this list will contains all blocks explored from root to this node.
            Block_info_father = []
            #print(Block_info_prev_lists)
            if Block_info_prev_lists:
                Block_info_temp = Block_info_prev_lists.pop(0)
                #for here we can use FIFO to find the father node, since we use bfs
                if Block_info_temp[-1] == Start_block_index :
                    Block_info = Block_info_temp
                    Block_info_father = Block_info_temp
                else: 
                    sys.exit ("Error in finding father node of Block_info_prev_lists")
                    
            
            Block_info = Block_info + Block_info_this_seg            
            
            string = "block"
            
            
            if add_ite:
                string_duplicate = Block_info[-4:]
                if len(Block_info) == 4:
                    Block_info_output = []
                    Block_info_prev_lists.append (Block_info[:2])
                    Block_info_prev_lists.append (Block_info[2:4])
                    
                else:
                    Block_info_output = Block_info[0:-4]
                    #add one branch node to block list for future children to find
                    Block_info_prev_lists.append (Block_info[0:-2])
                    #print(Block_info[0:-2])
                    #add second branch node to block list for future children to find
                    Block_info_prev_lists.append (Block_info[0:-4]+string_duplicate[2:4])
                    #print(Block_info[0:-4]+string_duplicate[2:4])    
            if add_ret: 
                string_duplicate = Block_info[-2:]            
                if len(Block_info) == 2:
                    Block_info_output = []
                else:
                    Block_info_output = Block_info[0:-2]
                    
                #basically, the ret means leaf node, there should not be any children use it. Hence no movement for Block_info_prev_lists
                #Block_info_prev_lists.append (Block_info)
    
            #now the number in block_info is like x-x-y-y-z-z            
            if Block_info_output :
                Block_info_output.insert(0,Block_info_output[0])
                Block_info_output.append(Block_info_output[-1])
            else :
                #append twice, since if the Block_info_output is empty, it means this node is a root.
                Block_info_output.append(Block_info[0])
                Block_info_output.append(Block_info[0])
            
            if Block_info_father :
                Block_info_father.insert(0,Block_info_father[0])
                Block_info_father.pop() #we pop here, since in the Block_info_prev_lists, the father node will be seperated into two branches when ite is called.

            #print(Block_info)        
            #extract x-y-z only
            odd =True
            for k in Block_info_output:
                if odd:
                    string = string + '_'+ str(k)    
                    odd =False
                else:
                    odd =True
            fout.write(string +"\n")
            
            string = "Father_Block:block"
            odd =True
            for k in Block_info_father:
                if odd:
                    string = string + '_'+ str(k)    
                    odd =False
                else:
                    odd =True
            fout.write(string +"\n")
            #print(i)
            #print(linelist[i])
            #print(string)
            
        fout.write(linelist[i])        
        i += 1
    fout.close()


def read_BB_info(linelist, i):
    """Extract basic block information from KLEE output.
    
    Args:
        linelist: List of lines from the KLEE output file
        i: Current line index
        
    Returns:
        list: A list with exactly 3 string elements [block_name, true_target, false_target]
              or None if the information cannot be extracted.
    """
    result = []
    
    # Bounds checking
    if i + 1 >= len(linelist) or i - 2 < 0:
        print(f"read_BB_info: index out of bounds at line {i}")
        return None
        
    add_ret = 'Inside Ret state.pc ++' in linelist[i+1]
    add_ite = 'Add constraint for trueStatement' in linelist[i+1]
    
    if 'block_' in linelist[i-2]:
        line = linelist[i-2]
        block_name = line[0:-1]  # remove "\n"
        
        if not block_name or not isinstance(block_name, str):
            print(f"read_BB_info: invalid block_name at line {i-2}")
            return None
            
        result.append(block_name)
        
        if add_ite:
            j = i + 1
            while j < len(linelist):
                if 'Father_Block:' in linelist[j] and block_name in linelist[j]:
                    line = linelist[j-1]
                    result.append(line[0:-1])
                    k = j + 1
                    while k < len(linelist):
                        if 'Father_Block:' in linelist[k] and block_name in linelist[k]:
                            line = linelist[k-1]
                            result.append(line[0:-1])
                            break
                        else:
                            k += 1
                    break
                else:
                    j += 1
        
        # For return statements, duplicate the block name
        if add_ret:
            result.append(line[0:-1])
            result.append(line[0:-1])
        
        # Validate we have exactly 3 elements
        if len(result) < 3:
            print(f"read_BB_info: incomplete result at line {i}: got {len(result)} elements, expected 3")
            return None
            
        # Validate all elements are non-empty strings
        for idx, elem in enumerate(result):
            if not elem or not isinstance(elem, str):
                print(f"read_BB_info: invalid element at position {idx}: '{elem}'")
                return None
                
        return result
    else:
        print(f"read_BB_info: 'block_' not found at line {i-2}")
        return None


'''
we just convert our cfg file to a more "z3 like " readable code
'''
def cfg_to_ir(finput, finput_reorder, foutput, islifter):
    """Convert CFG file to Z3-like intermediate representation.
    
    Returns:
        bool: True if conversion succeeded, False if KLEE output was malformed.
    """
    rewrite_add_constraint(finput, finput_reorder, islifter)
    add_block_info(finput_reorder, islifter)
    
    try:
        fin = open(finput_reorder, 'r')
        linelist = fin.readlines()
        fin.close()
    except (IOError, OSError) as e:
        print(f"cfg_to_ir: cannot read file {finput_reorder}: {e}")
        return False
        
    if not linelist:
        print(f"cfg_to_ir: empty input file {finput_reorder}")
        return False

    bb_info_errors = 0
    blocks_processed = 0
    
    try:
        fout = open(foutput, 'w')
    except (IOError, OSError) as e:
        print(f"cfg_to_ir: cannot write file {foutput}: {e}")
        return False
    
    i = 0
    while i < len(linelist) - 1:
        func_start = 'Function start' in linelist[i]
        add_ite = 'Add constraint for trueStatement' in linelist[i+1]
        if add_ite and func_start:
            # 1. read above two lines it should be:
            #    BB:[_a->_b] 
            #    BB:[_a->_c] appears            
            BB_info = read_BB_info(linelist, i)
            if BB_info is None:
                # Log but don't crash - skip this block
                bb_info_errors += 1
                print(f"cfg_to_ir: skipping malformed block at line {i}")
                i += 1
                continue
                
            blocks_processed += 1
            # 2. output let block_a =
            fout.write("###start\n") 
            fout.write("(let ((" + str(BB_info[0]) + "\n")            
            
            # 3. output let constraint_a = things between ---dump z3 start--- and ---dump z3 end---
            fout.write("(let ((constraint_" + str(BB_info[0]) + "\n")
            dump_start = i
            dump_end = i
            for k in range(i, len(linelist)):    
                if '----dump z3 start----' in linelist[k]:
                    dump_start = k
                if '----dump z3 end----' in linelist[k]:
                    dump_end = k
                    break
            for k in range(dump_start+2, dump_end):
                fout.write(linelist[k])
            fout.write("))")
            # 2. output ite constraint block_c block_b
            fout.write("(ite constraint_" + str(BB_info[0]) + " " + str(BB_info[1]) + " " + str(BB_info[2]) + " )\n")
            fout.write(")))\n")                
            fout.write("###end\n")
        
        add_ret = 'Inside Ret state.pc ++' in linelist[i+1]
        if add_ret and func_start:
            fout.write("###start\n") 
            # 1. read to above until first line of BB:[_a->_b]
            BB_info = read_BB_info(linelist, i)
            if BB_info is None:
                # Log but don't crash - skip this block
                bb_info_errors += 1
                print(f"cfg_to_ir: skipping malformed return block at line {i}")
                i += 1
                continue
                
            blocks_processed += 1
            # 2. output let block_a =
            fout.write("(let ((" + str(BB_info[0]) + "\n")
            # 3. output things between ---dump z3 start--- and ---dump z3 end---
            dump_start = i
            dump_end = i
            for k in range(i, len(linelist)):    
                if '----dump z3 start----' in linelist[k]:
                    dump_start = k
                if '----dump z3 end----' in linelist[k]:
                    dump_end = k
                    break
            # just dump pure expression
            for k in range(dump_start+2, dump_end):
                fout.write(linelist[k])
            fout.write("))\n")
            fout.write("###end\n")
        
        i += 1
    fout.close()
    
    if bb_info_errors > 0:
        print(f"cfg_to_ir: completed with {bb_info_errors} malformed blocks skipped, {blocks_processed} blocks processed")
    
    # Return False only if we got no blocks at all (complete failure)
    if blocks_processed == 0 and bb_info_errors > 0:
        print(f"cfg_to_ir: KLEE output appears to be completely malformed")
        return False
        
    return True
'''
Think about this, since we use bfs-klee to symbolic execute the bitcode, the info being dumped is from root to each leaves.
However, when we run the z3, we need to define those leaf nodes first. Hence, we need to revert the order of whole ir file.
'''
def ir_reorder(finput):
    """Reorder IR blocks from BFS order (root-to-leaf) to Z3 order (leaf-to-root).
    
    Returns:
        bool: True if reordering succeeded, False if file is empty or unreadable.
    """
    block_list = []
    try:
        fin = open(finput, 'r')
        linelist = fin.readlines()
        fin.close()
    except (IOError, OSError) as e:
        print(f"ir_reorder: cannot read file {finput}: {e}")
        return False
        
    if not linelist:
        print(f"ir_reorder: empty input file {finput}")
        return False
        
    i = 0
    while i < len(linelist):
        if '###start' in linelist[i]:
            j = i
            while j < len(linelist):
                if '###end' in linelist[j]:
                    result = []
                    result.append(i)
                    result.append(j)
                    block_list.append(result)
                    i = j
                    break
                else:
                    j += 1
        else:
            i += 1
            
    if not block_list:
        print(f"ir_reorder: no blocks found in {finput}")
        return False
        
    try:
        fout = open(finput, 'w')
        k = len(block_list) - 1 
        while k >= 0:
            for i in range(block_list[k][0], block_list[k][1]+1):
                fout.write(linelist[i])
            k -= 1
        fout.close()
    except (IOError, OSError) as e:
        print(f"ir_reorder: cannot write file {finput}: {e}")
        return False
        
    return True

def ir_to_z3_for_file(linelist,fout,root_name):
    block_list = []
    i = 0
    while i < len(linelist) :
        if '###start' in linelist[i]:
            j = i
            while j < len(linelist) :
                if '###end' in linelist[j]:
                    result = []
                    result.append(i)
                    result.append(j)
                    block_list.append(result)
                    i = j
                    break
                else:
                    j += 1
        else:
            i += 1
    #print (block_list)
    k = 0 
    while k < len(block_list) :
        for i in range(block_list[k][0]+1,block_list[k][1]):
            fout.write(linelist[i])
        k += 1
    #we print block_0 here, since block_0 should be root
    fout.write (root_name+")\n")
    for i in range(len(block_list)):
        fout.write(")")    
    fout.write("\n")


def find_root(linelist):
    """Find the root block name in the IR file.
    
    Returns:
        str: The root block name, or None if not found.
    """
    k = len(linelist) - 1
    while k >= 0:
        if '###start' in linelist[k]:
            if k + 1 < len(linelist) and 'block_' in linelist[k+1]:
                match = re.search(r'\(let \(\((.+?)\n', linelist[k+1])
                if match:
                    root_name = str(match.group(1))
                    return root_name
                else:
                    print(f"find_root: regex failed to match at line {k+1}")
                    return None
        k -= 1
    print("find_root: no root block found in IR file")
    return None
        



def ir_to_z3(finput_lifter_original, finput_lifter, finput_decompiler, foutput):
    """Convert IR files to Z3 formula for equivalence checking.
    
    Returns:
        tuple: (success: bool, unsat: bool)
        - success: True if conversion completed, False if input files were malformed
        - unsat: True if the formula should be checked for unsat (multi-arg case)
    """
    num_bits = "2048" 
    num_byte = 256 
    
    # Read lifter original file
    try:
        fin = open(finput_lifter_original, 'r')
        linelist = fin.readlines()
        fin.close()
    except (IOError, OSError) as e:
        print(f"ir_to_z3: cannot read {finput_lifter_original}: {e}")
        return (False, False)
    
    if not linelist:
        print(f"ir_to_z3: empty angr IR file {finput_lifter_original}")
        return (False, False)

    declare_list_angr = []
    declare_list_angr_variable = []
    declare_list_angr_variable_isarray = {}
    declare_list_prompt = []
    declare_list_prompt_variable = []

    unsat = False
    #declare variables in lifter
    i = 0
    while i < len(linelist) :
        if '(declare-fun' in linelist[i]:
            match = re.search(r'\(declare-fun (.+?) \(\) (.+?)\n', linelist[i])
            if match:
                variable_name = match.group(1)
                variable_type = match.group(2)
                declare_list_angr.append("(declare-const "+ variable_name +" "+variable_type+"\n")
                if "2048" in variable_type:
                    declare_list_angr_variable_isarray[variable_name] = True
                else:
                    declare_list_angr_variable_isarray[variable_name] = False
                if 'angr_' in linelist[i]:
                    declare_list_angr_variable.append(variable_name)
        i += 1
    #prompt_arg_name = re.search('Function:  (.+?)\n',linelist[1]).group(1)
    prompt_arg_name = "prompt_args"
    
    # Read decompiler file
    try:
        fin = open(finput_decompiler, 'r')
        linelist = fin.readlines()
        fin.close()
    except (IOError, OSError) as e:
        print(f"ir_to_z3: cannot read {finput_decompiler}: {e}")
        return (False, False)
        
    if not linelist:
        print(f"ir_to_z3: empty decompiler IR file {finput_decompiler} - KLEE may have failed")
        return (False, False)
    #print(prompt_arg_name)
    #declare variables in decompiler
    i = 0
    while i < len(linelist) :
        if prompt_arg_name in linelist[i]:
            all_pieces = linelist[i][:-1].split(' ')
            j = 0
            while j < len(all_pieces) :
                if prompt_arg_name in all_pieces[j] :
                    variable_name = all_pieces[j]
                    declare_list_prompt.append("(declare-const "+ variable_name +" (Array (_ BitVec 32) (_ BitVec 8)))\n")
                    declare_list_prompt_variable.append(variable_name)
                    
                    
                j += 1
        i += 1    
    
    
    fout = open(foutput,'w')
    
    
    #remove duplicated variables
    declare_list_angr = list(set(declare_list_angr))
    declare_list_prompt = list(set(declare_list_prompt))    

    #decalre found variables
    i = 0
    while i < len(declare_list_angr):
        fout.write(declare_list_angr[i])
        i += 1

    i = 0
    while i < len(declare_list_prompt):
        fout.write(declare_list_prompt[i])
        i += 1


    #we want to assert variables from angr = variables from prompt
    declare_list_prompt_variable = list(set(declare_list_prompt_variable))
    declare_list_angr_variable = list(set(declare_list_angr_variable))
    if len(declare_list_prompt_variable) > 10 or len(declare_list_angr_variable) > 10:
        fout.write("multiple args assignment need to assert variables equavilent by yourself")
    elif len(declare_list_prompt_variable) > 0 or len(declare_list_angr_variable)> 0:
        unsat = True
        if len(declare_list_prompt_variable)  == len(declare_list_angr_variable) :
            for i in range(len(declare_list_angr_variable)):
                choice_declare_list_angr_variable = declare_list_angr_variable[i]
                choice_declare_list_angr_variable_is_array = declare_list_angr_variable_isarray[choice_declare_list_angr_variable]
                index_of_angr_variable = int(re.search('angr_arg(.+?)_(.+?)',choice_declare_list_angr_variable).group(1),10)
                print("multiple arguments\n")
                print(index_of_angr_variable)
                choice_declare_list_prompt_variable = "Unknown"
                for j in range(len(declare_list_prompt_variable)):
                    index_of_prompt_variable = int(re.search('prompt_args_(.+?)_ar',declare_list_prompt_variable[j]).group(1),10)
                    if index_of_prompt_variable == index_of_angr_variable : 
                        choice_declare_list_prompt_variable = declare_list_prompt_variable[j]
                        break
                print(index_of_prompt_variable)
                '''
                fout.write("(assert \n")
                fout.write("(= " + choice_declare_list_angr_variable )
                fout.write(" (concat (select "+choice_declare_list_prompt_variable +" #x00000007)\n(concat (select " + choice_declare_list_prompt_variable +" #x00000006)\n(concat (select "+choice_declare_list_prompt_variable + " #x00000005)\n")
                fout.write("(concat (select "+choice_declare_list_prompt_variable +" #x00000004)\n(concat (select " + choice_declare_list_prompt_variable +" #x00000003)\n(concat (select "+choice_declare_list_prompt_variable + " #x00000002)\n")
                fout.write("(concat (select "+choice_declare_list_prompt_variable +" #x00000001)\n(concat (select " + choice_declare_list_prompt_variable +" #x00000000)))))))))\n")
                fout.write(")) \n")
                '''
                if choice_declare_list_angr_variable_is_array == True:
                    fout.write("(assert \n")
                    fout.write("(= " + choice_declare_list_angr_variable )
                    for counter in range(num_byte):
                        fout.write("\n (concat (select "+choice_declare_list_prompt_variable +" #x"+ format(counter, '08x')+")")
                    for counter in range(num_byte):
                        fout.write(")")
                    fout.write("\n")
                    fout.write(")) \n")
                else:
                    fout.write("(assert \n")
                    fout.write("(= " + choice_declare_list_angr_variable )
                    fout.write(" (concat (select "+choice_declare_list_prompt_variable +" #x00000007)\n(concat (select " + choice_declare_list_prompt_variable +" #x00000006)\n(concat (select "+choice_declare_list_prompt_variable + " #x00000005)\n")
                    fout.write("(concat (select "+choice_declare_list_prompt_variable +" #x00000004)\n(concat (select " + choice_declare_list_prompt_variable +" #x00000003)\n(concat (select "+choice_declare_list_prompt_variable + " #x00000002)\n")
                    fout.write("(concat (select "+choice_declare_list_prompt_variable +" #x00000001)\n(concat (select " + choice_declare_list_prompt_variable +" #x00000000)))))))))\n")
                    fout.write(")) \n")
        else:
            pass
            #fout.write("multiple args with number of args are not same!!!")
    else :
        unsat = False
    
    fout.write("(assert \n")
    fout.write("\n(let\n(\n(angr\n")
    
    # Read and process lifter IR
    try:
        fin = open(finput_lifter, 'r')
        linelist = fin.readlines()
        fin.close()
    except (IOError, OSError) as e:
        print(f"ir_to_z3: cannot read lifter IR file {finput_lifter}: {e}")
        fout.close()
        return (False, False)
        
    if not linelist:
        print(f"ir_to_z3: empty lifter IR file {finput_lifter}")
        fout.close()
        return (False, False)
        
    root_name = find_root(linelist)
    if root_name is None:
        print(f"ir_to_z3: could not find root block in lifter IR - ANGR analysis may have failed")
        fout.close()
        return (False, False)
        
    ir_to_z3_for_file(linelist, fout, root_name)
    fout.write("    (prompt \n")
    
    # Read and process decompiler IR
    try:
        fin = open(finput_decompiler, 'r')
        linelist = fin.readlines()
        fin.close()
    except (IOError, OSError) as e:
        print(f"ir_to_z3: cannot read decompiler IR file {finput_decompiler}: {e}")
        fout.close()
        return (False, False)
        
    if not linelist:
        print(f"ir_to_z3: empty decompiler IR file {finput_decompiler} - KLEE symbolic execution may have failed")
        fout.close()
        return (False, False)
        
    root_name = find_root(linelist)
    if root_name is None:
        print(f"ir_to_z3: could not find root block in decompiler IR - KLEE output may be malformed")
        fout.close()
        return (False, False)
        
    ir_to_z3_for_file(linelist, fout, root_name)
    
    if unsat == True:
        fout.write(")\n ( not (= angr prompt))\n))")
    else:
        fout.write(")\n ( = angr prompt)\n))")
    

    fout.write("\n(check-sat)")
    fout.close()
    
    if unsat == True:
        fin = open(foutput, 'r')
        linelist = fin.readlines()
        fin.close()
        os.system("rm "+ foutput)
        fout = open(foutput+"_unsat",'w')
        i = 0
        while i < len(linelist):
            fout.write(linelist[i])
            i += 1    
        fout.close()
    return (True, unsat)

def main():
    cfg_to_ir(file_name_lifter,file_reorder_lifter,file_ir_lifter,True)
    cfg_to_ir(file_name_decompiler,file_reorder_decompiler,file_ir_decompiler,False)
    ir_reorder(file_ir_lifter)
    ir_reorder(file_ir_decompiler)
    ir_to_z3("/tmp/angr.txt",file_ir_lifter,file_ir_decompiler,file_z3)

if __name__ == "__main__":
    main()

    
