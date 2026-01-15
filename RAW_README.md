1. ubuntu 20.04 container

mkdir -p /root/work
cd /root/work && git clone https://github.com/tbd-mavenkoders/D-helix-fixed.git

cd /root

2. a install these packages
apt-get update && apt-get install -y \
    build-essential \
    git \
    wget \
    curl \
    software-properties-common \
    cmake \
    ninja-build \
    pkg-config \
    python3-pip \
    python3-dev \
    python3-venv \
    libffi-dev \
    libssl-dev \
    libtcmalloc-minimal4 \
    libgoogle-perftools-dev \
    libncurses5-dev \
    libsqlite3-dev \
    libcap-dev \
    zlib1g-dev \
    libbz2-dev \
    libreadline-dev \
    libxml2-dev \
    libxslt1-dev \
    default-jdk \
    unzip \
    vim \
    nano \
    sudo

2. b
apt-get update && \
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


3. install gcc 11

cd /root
add-apt-repository -y ppa:ubuntu-toolchain-r/test
apt-get update
apt-get install -y gcc-11 g++-11
update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-11 110
update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-11 110
gcc --version

4. install clang 16

cd /root
wget https://apt.llvm.org/llvm.sh
chmod +x llvm.sh
./llvm.sh 16
update-alternatives --install /usr/bin/clang clang /usr/bin/clang-16 160
update-alternatives --install /usr/bin/clang++ clang++ /usr/bin/clang++-16 160
clang --version


5. install llvm 3.8

cd /root
wget https://releases.llvm.org/3.8.0/clang+llvm-3.8.0-x86_64-linux-gnu-ubuntu-14.04.tar.xz
tar -xf clang+llvm-3.8.0-x86_64-linux-gnu-ubuntu-14.04.tar.xz
mv clang+llvm-3.8.0-x86_64-linux-gnu-ubuntu-14.04 llvm-3.8
export PATH="/root/llvm-3.8/bin:$PATH"
echo 'export PATH="/root/llvm-3.8/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

5. z3

cd /root
wget https://github.com/Z3Prover/z3/releases/download/z3-4.9.1/z3-4.9.1-x64-glibc-2.31.zip
unzip z3-4.9.1-x64-glibc-2.31.zip
mv z3-4.9.1-x64-glibc-2.31 z3

# Add to PATH and set library path
echo 'export PATH="/root/z3/bin:$PATH"' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH="/root/z3/bin:$LD_LIBRARY_PATH"' >> ~/.bashrc
echo 'export PYTHONPATH="/root/z3/bin/python:$PYTHONPATH"' >> ~/.bashrc
source ~/.bashrc

# Verify
z3 --version

6. install and patch angr

a. 
pip3 install virtualenv

# Clone angr-dev
git clone https://github.com/angr/angr-dev.git
cd angr-dev

# Checkout the specific commit for Vex IR
git checkout b2198226e6194310c57a4b50ae9a6c82b1b6cd7f

dpkg --add-architecture i386
apt-get update
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
    libc6-dev-i386

./setup.sh -e angr

source /root/.virtualenvs/angr/bin/activate
pip install "setuptools==67.8.0" "pip==23.3.2"


cd /root/angr-dev

cd /root/angr-dev/archinfo && git checkout 4eea2b81e78a2d902d6c7c0ff7168b304b9d3b8c
cd /root/angr-dev/pyvex && git checkout de7f92e126fbbaa61287e2a647be6f2871d56032
cd /root/angr-dev/cle && git checkout 7024cd3fc479af221cc3070b0ddca1ac20ca1a22
cd /root/angr-dev/claripy && git checkout 91518043156fc317195a577a6c8b41763c138577
cd /root/angr-dev/ailment && git checkout cb3205ffcb182632840d9b745a8f42b5d259a4b6
cd /root/angr-dev/angr && git checkout 6ef773615ff70c5c334ee16945e22e9005a8c82d

cd /root/angr-dev

pip install --no-build-isolation -e ./archinfo
pip install --no-build-isolation -e ./pyvex
pip install --no-build-isolation -e ./cle
pip install --no-build-isolation -e ./claripy
pip install --no-build-isolation -e ./ailment
pip install --no-build-isolation -e ./angr

6. b patching angr 

source /root/.virtualenvs/angr/bin/activate
cd /root/angr-dev

cd /root/angr-dev/angr
patch -p1 < /root/work/D-helix-fixed/D-helix/angr_vexir_diff.patch

cd /root/angr-dev/claripy
patch -p1 < /root/work/D-helix-fixed/D-helix/claripy_vexir_diff.patch

cp /root/work/D-helix-fixed/D-helix/muqi.py /root/angr-dev/angr/angr/

ls -la /root/angr-dev/angr/angr/muqi.py

pip uninstall -y capstone
pip install capstone==4.0.2

source /root/.virtualenvs/angr/bin/activate
cd /root/angr-dev/pyvex

# Clean and rebuild
pip uninstall -y pyvex
python setup.py build
pip install --no-build-isolation -e .


# to finally verify angr

python -c "import pyvex; print('pyvex loaded')"
python -c "import angr; print('angr version:', angr.__version__)"


7. install klee-ulibc

cd /root
git clone https://github.com/klee/klee-uclibc.git
cd klee-uclibc


apt-get install -y libncurses5-dev libncursesw5-dev
apt-get install -y gcc-multilib g++-multilib

cp /usr/lib/gcc/x86_64-linux-gnu/9/crt*.o /usr/lib/

# Copy the missing libgcc libraries as well (to prevent the next error)
cp /usr/lib/gcc/x86_64-linux-gnu/9/libgcc* /usr/lib/

#  Go back to the build folder
cd /root/klee-uclibc

# Configure 
./configure --make-llvm-lib \
  --with-llvm-config /root/llvm-3.8/bin/llvm-config \
  --with-cc /root/llvm-3.8/bin/clang

# Build
make -j$(nproc)

8. PROMPT setup

apt-get install -y libgoogle-perftools-dev
apt-get install -y flex bison
python -m pip install lit

cd /root

git clone https://github.com/sysrel/PROMPT.git
cd PROMPT

patch -p1 < /root/work/D-helix-fixed/D-helix/prompt_diff.patch

# Create build directory
mkdir build && cd build



cmake \
  -DCMAKE_CXX_FLAGS="-D_GLIBCXX_USE_CXX11_ABI=0" \
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
  ../



cp /root/PROMPT/lib/Solver/Z3Builder.h /root/PROMPT/lib/Expr/
cd /root/PROMPT/build

# patch the llvm header ( valuemap error )
sed -i 's/return MDMap;/return (bool)MDMap;/g' /root/llvm-3.8/include/llvm/IR/ValueMap.h

# copy z3builder.h to the right place 

cp /root/PROMPT/lib/Expr/Z3Builder.h /root/PROMPT/lib/Core/

# inject header function

sed -i '/Z3ASTHandle construct_muqi_solver(ref<Expr> e, int \*width_out);/a \\tZ3ASTHandle construct_muqi(ref<Expr> e, int width) { int w = width; return construct_muqi_solver(e, \&w); }' /root/PROMPT/lib/Core/Z3Builder.h

#  Remove the line we added previously (to avoid duplicates)
sed -i '/construct_muqi(ref<Expr>/d' /root/PROMPT/lib/Core/Z3Builder.h

#  Insert the function again, but explicitly add "public:" to force visibility
sed -i '/Z3ASTHandle construct_muqi_solver(ref<Expr> e, int \*width_out);/a public: Z3ASTHandle construct_muqi(ref<Expr> e, int width) { int w = width; return construct_muqi_solver(e, \&w); }' /root/PROMPT/lib/Core/Z3Builder.h


# Remove the previous incorrect patch
sed -i '/construct_muqi(ref<Expr>/d' /root/PROMPT/lib/Core/Z3Builder.h

# Insert the CORRECTED patch (Public + Pointer argument)
sed -i '/Z3ASTHandle construct_muqi_solver(ref<Expr> e, int \*width_out);/a public: Z3ASTHandle construct_muqi(ref<Expr> e, int *width) { return construct_muqi_solver(e, width); }' /root/PROMPT/lib/Core/Z3Builder.h

9. Install ghidra

cd /root

# Download Ghidra 10.0
wget https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_10.0_build/ghidra_10.0_PUBLIC_20210621.zip

# Unzip
unzip ghidra_10.0_PUBLIC_20210621.zip
mv ghidra_10.0_PUBLIC ghidra

# Add Ghidra to PATH
echo 'export GHIDRA_HOME="/root/ghidra"' >> ~/.bashrc
echo 'export PATH="$GHIDRA_HOME:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Verify Java is available (Ghidra needs it)
java -version


10. final configuration

# Add PROMPT/klee to PATH
echo 'export PATH="/root/PROMPT/build/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Verify all components
echo "=== Checking PROMPT/KLEE ===" 
/root/PROMPT/build/bin/klee --version 2>/dev/null || /root/PROMPT/build/bin/klee --version

echo "=== Checking angr ===" 
source /root/.virtualenvs/angr/bin/activate
python -c "import angr; print('angr version:', angr.__version__)"

echo "=== Checking Z3 ===" 
z3 --version

echo "=== Checking Ghidra ===" 
ls /root/ghidra/ghidraRun

echo "=== Checking clang-3.8 ===" 
/root/llvm-3.8/bin/clang --version


11. additional steps

source /root/.virtualenvs/angr/bin/activate
pip install wrapt-timeout-decorator six numpy

source /root/.virtualenvs/angr/bin/activate
echo $PATH

# Add klee to the angr venv's activation script
echo 'export PATH="/root/PROMPT/build/bin:$PATH"' >> /root/.virtualenvs/angr/bin/activate

# Deactivate and reactivate to apply
deactivate
source /root/.virtualenvs/angr/bin/activate

# Test klee now
klee --version
which klee



12. Simple test program creation

# Navigate to D_helix_angr
cd /root/work/D-helix-fixed/D-helix/D_helix_angr

# Create test directory structure
mkdir -p function_name
mkdir -p test_muqi/originalclang
mkdir -p test_muqi/generated_whole_c
mkdir -p test_muqi/generated_html
mkdir -p test_muqi/generated_function_c
mkdir -p test_muqi/generatedbc
mkdir -p test_muqi/model_prompt
mkdir -p test_muqi/z3
mkdir -p test_muqi/log
mkdir -p test_muqi/generated_function_c/project_folder
mkdir -p test_muqi/generated_function_c/log_for_compile
mkdir -p test_muqi/generatedll
mkdir -p test_muqi/generatedklee
mkdir -p test_muqi/diff


# Create a simple test C program
cat > /tmp/test_simple.c << 'EOF'
#include <stdio.h>

int add(int a, int b) {
    return a + b;
}

int subtract(int a, int b) {
    return a - b;
}

int main() {
    int x = 5;
    int y = 3;
    printf("Add: %d\n", add(x, y));
    printf("Sub: %d\n", subtract(x, y));
    return 0;
}
EOF

# Compile with clang-16 to create test binary
clang-16 -O0 -g /tmp/test_simple.c -o test_muqi/originalclang/test_simple

# Verify binary was created
ls -lh test_muqi/originalclang/
file test_muqi/originalclang/test_simple