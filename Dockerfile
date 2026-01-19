# Step 1: Base Image
FROM ubuntu:20.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Set working directory to /root as per instructions
WORKDIR /root

# --- Step 1 & 2a: Dependencies ---
RUN apt-get update && apt-get install -y \
    build-essential git wget curl software-properties-common cmake ninja-build \
    pkg-config python3-pip python3-dev python3-venv libffi-dev libssl-dev \
    libtcmalloc-minimal4 libgoogle-perftools-dev libncurses5-dev libsqlite3-dev \
    libcap-dev zlib1g-dev libbz2-dev libreadline-dev libxml2-dev libxslt1-dev \
    default-jdk unzip vim nano sudo && \
    mkdir -p /root/work && \
    cd /root/work && git clone https://github.com/tbd-mavenkoders/D-helix-fixed.git

# --- Step 2b: Python 3.8 Setup ---
RUN apt-get update && \
    apt-get install -y software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa -y && \
    apt-get update && \
    apt-get install -y python3.8 python3.8-dev python3.8-venv python3-pip \
    git build-essential cmake wget unzip libncurses5 libz-dev libtinfo5 \
    pixz xz-utils curl vim && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.8 1 && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.8 1 && \
    ln -sf /usr/bin/python3.8 /usr/bin/python && \
    python -m pip install --upgrade pip

# --- Step 3: GCC 11 ---
RUN add-apt-repository -y ppa:ubuntu-toolchain-r/test && \
    apt-get update && \
    apt-get install -y gcc-11 g++-11 && \
    update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-11 110 && \
    update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-11 110

# --- Step 4: Clang 16 ---
RUN wget https://apt.llvm.org/llvm.sh && \
    chmod +x llvm.sh && \
    ./llvm.sh 16 && \
    update-alternatives --install /usr/bin/clang clang /usr/bin/clang-16 160 && \
    update-alternatives --install /usr/bin/clang++ clang++ /usr/bin/clang++-16 160

# --- Step 5: LLVM 3.8 & Z3 ---
# LLVM 3.8
RUN wget https://releases.llvm.org/3.8.0/clang+llvm-3.8.0-x86_64-linux-gnu-ubuntu-14.04.tar.xz && \
    tar -xf clang+llvm-3.8.0-x86_64-linux-gnu-ubuntu-14.04.tar.xz && \
    mv clang+llvm-3.8.0-x86_64-linux-gnu-ubuntu-14.04 llvm-3.8

# Z3
RUN wget https://github.com/Z3Prover/z3/releases/download/z3-4.9.1/z3-4.9.1-x64-glibc-2.31.zip && \
    unzip z3-4.9.1-x64-glibc-2.31.zip && \
    mv z3-4.9.1-x64-glibc-2.31 z3

# Set Persistent Environment Variables for LLVM/Z3
ENV PATH="/root/llvm-3.8/bin:/root/z3/bin:${PATH}"
ENV LD_LIBRARY_PATH="/root/z3/bin:${LD_LIBRARY_PATH}"
ENV PYTHONPATH="/root/z3/bin/python:${PYTHONPATH}"

# --- Step 6: Angr Setup & Patching ---
# We combine these to keep layers smaller. 
# Note: Virtualenv activation in Docker requires specific handling. 
# We will install packages into the venv by calling the venv's pip directly.
RUN pip3 install virtualenv && \
    git clone https://github.com/angr/angr-dev.git && \
    cd angr-dev && \
    git checkout b2198226e6194310c57a4b50ae9a6c82b1b6cd7f && \
    \
    dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y \
        openjdk-8-jdk \
        zlib1g:i386 \
        libtinfo5:i386 \
        libstdc++6:i386 \
        libgcc1:i386 \
        libc6:i386 \
        nasm \
        binutils-multiarch \
        qtdeclarative5-dev \
        libpixman-1-dev \
        libglib2.0-dev \
        debian-archive-keyring \
        debootstrap \
        libtool \
        libc6-dev-i386 && \
    \
    # force old tooling BEFORE setup installs anything
    export ANGR_NO_PIP_UPGRADE=1 && \
    ./setup.sh -e angr && \
    \
    # now downgrade inside the created venv
    /root/.virtualenvs/angr/bin/pip install \
        "pip==23.3.2" \
        "setuptools==67.8.0" \
        "wheel<0.41" && \
    \
    # checkout pinned commits
    cd /root/angr-dev/archinfo && git checkout 4eea2b81e78a2d902d6c7c0ff7168b304b9d3b8c && \
    cd /root/angr-dev/pyvex && git checkout de7f92e126fbbaa61287e2a647be6f2871d56032 && \
    cd /root/angr-dev/cle && git checkout 7024cd3fc479af221cc3070b0ddca1ac20ca1a22 && \
    cd /root/angr-dev/claripy && git checkout 91518043156fc317195a577a6c8b41763c138577 && \
    cd /root/angr-dev/ailment && git checkout cb3205ffcb182632840d9b745a8f42b5d259a4b6 && \
    cd /root/angr-dev/angr && git checkout 6ef773615ff70c5c334ee16945e22e9005a8c82d && \
    \
    # reinstall editable repos cleanly
    /root/.virtualenvs/angr/bin/pip install --no-build-isolation -e /root/angr-dev/archinfo && \
    /root/.virtualenvs/angr/bin/pip install --no-build-isolation -e /root/angr-dev/pyvex && \
    /root/.virtualenvs/angr/bin/pip install --no-build-isolation -e /root/angr-dev/cle && \
    /root/.virtualenvs/angr/bin/pip install --no-build-isolation -e /root/angr-dev/claripy && \
    /root/.virtualenvs/angr/bin/pip install --no-build-isolation -e /root/angr-dev/ailment && \
    /root/.virtualenvs/angr/bin/pip install --no-build-isolation -e /root/angr-dev/angr

# Apply patches to Angr
RUN cd /root/angr-dev/angr && patch -p1 < /root/work/D-helix-fixed/D-helix/angr_vexir_diff.patch && \
    cd /root/angr-dev/claripy && patch -p1 < /root/work/D-helix-fixed/D-helix/claripy_vexir_diff.patch && \
    cp /root/work/D-helix-fixed/D-helix/muqi.py /root/angr-dev/angr/angr/ && \
    /root/.virtualenvs/angr/bin/pip uninstall -y capstone && \
    /root/.virtualenvs/angr/bin/pip install capstone==4.0.2 && \
    /root/.virtualenvs/angr/bin/pip uninstall -y pyvex && \
    cd /root/angr-dev/pyvex && /root/.virtualenvs/angr/bin/python setup.py build && \
    /root/.virtualenvs/angr/bin/pip install --no-build-isolation -e .

# --- Step 7: KLEE-uClibc ---
RUN git clone https://github.com/klee/klee-uclibc.git && \
    cd klee-uclibc && \
    apt-get install -y libncurses5-dev libncursesw5-dev gcc-multilib g++-multilib && \
    cp /usr/lib/gcc/x86_64-linux-gnu/9/crt*.o /usr/lib/ && \
    cp /usr/lib/gcc/x86_64-linux-gnu/9/libgcc* /usr/lib/ && \
    ./configure --make-llvm-lib \
      --with-llvm-config /root/llvm-3.8/bin/llvm-config \
      --with-cc /root/llvm-3.8/bin/clang && \
    make -j$(nproc)

# --- Step 8: PROMPT ---
RUN apt-get install -y libgoogle-perftools-dev flex bison && \
    python -m pip install lit && \
    git clone https://github.com/sysrel/PROMPT.git && \
    cd PROMPT && \
    patch -p1 < /root/work/D-helix-fixed/D-helix/prompt_diff.patch && \
    mkdir build && cd build && \
    cmake -DCMAKE_CXX_FLAGS="-D_GLIBCXX_USE_CXX11_ABI=0" \
      -DENABLE_TCMALLOC=ON \
      -DENABLE_POSIX_RUNTIME=ON \
      -DENABLE_KLEE_UCLIBC=ON \
      -DKLEE_UCLIBC_PATH=/root/klee-uclibc \
      -DENABLE_SOLVER_Z3=ON \
      -DENABLE_SOLVER_STP=OFF \
      -DENABLE_SOLVER_METASMT=OFF \
      -DENABLE_UNIT_TESTS=OFF \
      -DENABLE_SYSTEM_TESTS=OFF \
      -DLLVM_CONFIG_BINARY=/root/llvm-3.8/bin/llvm-config \
      -DLLVMCC=/root/llvm-3.8/bin/clang \
      -DLLVMCXX=/root/llvm-3.8/bin/clang++ \
      ../ && \
    # Patch files as per instructions
    cp /root/PROMPT/lib/Solver/Z3Builder.h /root/PROMPT/lib/Expr/ && \
    sed -i 's/return MDMap;/return (bool)MDMap;/g' /root/llvm-3.8/include/llvm/IR/ValueMap.h && \
    cp /root/PROMPT/lib/Expr/Z3Builder.h /root/PROMPT/lib/Core/ && \
    sed -i '/Z3ASTHandle construct_muqi_solver(ref<Expr> e, int \*width_out);/a public: Z3ASTHandle construct_muqi(ref<Expr> e, int *width) { return construct_muqi_solver(e, width); }' /root/PROMPT/lib/Core/Z3Builder.h && \
    make -j$(nproc)

# --- Step 9: Ghidra ---
RUN wget https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_10.0_build/ghidra_10.0_PUBLIC_20210621.zip && \
    unzip ghidra_10.0_PUBLIC_20210621.zip && \
    mv ghidra_10.0_PUBLIC ghidra && \
    rm ghidra_10.0_PUBLIC_20210621.zip

ENV GHIDRA_HOME="/root/ghidra"
ENV PATH="$GHIDRA_HOME:$PATH"

# --- Step 10 & 11: Final Config ---
ENV PATH="/root/PROMPT/build/bin:$PATH"

# Install python deps into the angr venv
RUN /root/.virtualenvs/angr/bin/pip install wrapt-timeout-decorator six numpy

# --- Step 12: Test Setup ---
# Create test directory structure
RUN cd /root/work/D-helix-fixed/D-helix/D_helix_angr && \
    mkdir -p function_name test_muqi/originalclang test_muqi/generated_whole_c \
    test_muqi/generated_html test_muqi/generated_function_c test_muqi/generatedbc \
    test_muqi/model_prompt test_muqi/z3 test_muqi/log \
    test_muqi/generated_function_c/project_folder \
    test_muqi/generated_function_c/log_for_compile \
    test_muqi/generatedll test_muqi/generatedklee test_muqi/diff

# Create a simple test binary
RUN echo '#include <stdio.h>\n\
int add(int a, int b) { return a + b; }\n\
int subtract(int a, int b) { return a - b; }\n\
int main() {\n\
    int x = 5, y = 3;\n\
    printf("Add: %d\\n", add(x, y));\n\
    printf("Sub: %d\\n", subtract(x, y));\n\
    return 0;\n\
}' > /tmp/test_simple.c && \
    clang-16 -O0 -g /tmp/test_simple.c -o /root/work/D-helix-fixed/D-helix/D_helix_angr/test_muqi/originalclang/test_simple_2

# --- Step 13: Install FastAPI Dependencies ---
RUN cd /root/work/D-helix-fixed/fastapi_server && \
    /root/.virtualenvs/angr/bin/pip install -r requirements_api.txt

# Expose FastAPI port
EXPOSE 10012

# Set working directory to fastapi_server
WORKDIR /root/work/D-helix-fixed/fastapi_server

# Default command: Start FastAPI server with single worker
# For multiple workers, override with: docker run -p 10012:10012 d-helix uvicorn api_server:app --host 0.0.0.0 --port 10012 --workers 12
CMD ["/root/.virtualenvs/angr/bin/python", "api_server.py"]
