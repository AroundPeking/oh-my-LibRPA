---
name: gw-toolchain
description: GW toolchain installation (OneAPI, GCC, ELPA, LibXC, LibRPA, FHI-aims, PYATB, ABACUS) on remote servers
---

# GW Toolchain - Remote Server Installation

Automated installation workflow for compiling FHI-aims, LibRPA, PYATB, and ABACUS on remote Linux servers. Automatically detects server environment (CPU architecture, existing installations, OneAPI versions) and adapts the installation process accordingly.

## How It Works

The skill follows this workflow:

1. **Server Connection** - Connect to remote server via SSH (uses saved aliases or host/username)
2. **Environment Detection** - Detect CPU architecture, existing installations, OneAPI version, MKL paths
3. **Dependency Installation** - Install OneAPI, cmake, Python, GCC (if needed)
4. **Component Installation** - Install LibRPA, FHI-aims, PYATB, ABACUS in order
5. **Environment Configuration** - Update .bashrc with necessary environment variables

## When to Use

Use `/gw-toolchain` when:
- Setting up a new DFT computing server
- Migrating to a new server
- Reinstalling the full software stack
- Need automated, reproducible installation

## Environment Detection

The skill automatically detects:

| Property | Detection Method | Purpose |
|----------|-----------------|---------|
| CPU Architecture | `lscpu \| grep "Model name"` | Set optimization flags (AVX512, AVX2, etc.) |
| OneAPI Version | `ls /opt/intel/oneapi/` | Set correct compiler names (icpx vs icpc) and MKL paths |
| Existing GCC | `which gcc && gcc --version` | Decide if GCC installation is needed |
| MPI Type | `which mpicc && mpicc --version` | Determine MPI compiler commands |
| Python Version | `python3 --version` | Verify Python environment |

## Installation Steps

### 0. Pre-Installation Check

Before starting, verify server basic status:

```bash
# Check system info
echo "=== System Information ==="
echo "OS: $(cat /etc/os-release | grep PRETTY_NAME)"
echo "Kernel: $(uname -r)"
echo "Architecture: $(uname -m)"
echo "CPU: $(lscpu | grep 'Model name' | cut -d: -f2 | xargs)"
echo "Cores: $(nproc)"
echo "Memory: $(free -h | grep Mem | awk '{print $2}')"
echo "Disk: $(df -h /home | tail -n 1 | awk '{print $4}') available"

# Check existing installations
echo -e "\n=== Existing Software ==="
command -v ifx >/dev/null 2>&1 && echo "OneAPI: $(ifx --version | head -n 1)" || echo "OneAPI: NOT INSTALLED"
command -v gcc >/dev/null 2>&1 && echo "GCC: $(gcc --version | head -n 1)" || echo "GCC: NOT INSTALLED"
command -v cmake >/dev/null 2>&1 && echo "CMake: $(cmake --version | head -n 1)" || echo "CMake: NOT INSTALLED"
command -v python3 >/dev/null 2>&1 && echo "Python: $(python3 --version)" || echo "Python: NOT INSTALLED"
```

### 1. Server Connection

First, connect to the server using SSH:

```bash
# Option 1: Use saved alias (recommended)
mcp__ssh__connect alias="your-server-alias"

# Option 2: Direct connection
mcp__ssh__connect host="server.example.com" username="user" password="your-password"
```

### 2. Install OneAPI (Base & HPCKit)

```bash
# Detect OneAPI version automatically
ONEAPI_VERSION=$(ls /opt/intel/oneapi/ 2>/dev/null | grep -E "^[0-9]" | sort -V | tail -n 1)

# If not installed, add Intel repository and install
wget -qO- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | sudo gpg --dearmor --output /usr/share/keyrings/oneapi-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main" | sudo tee /etc/apt/sources.list.d/oneAPI.list
sudo apt update
sudo apt install intel-basekit intel-hpckit

# Add to ~/.bashrc
echo 'source /opt/intel/oneapi/setvars.sh > /dev/null' >> ~/.bashrc
source ~/.bashrc
```

**Verification:**

```bash
# Verify OneAPI installation
echo "=== OneAPI Installation Check ==="
source /opt/intel/oneapi/setvars.sh > /dev/null

# Check compilers
echo -n "Intel C++ Compiler (icpx): "
if command -v icpx >/dev/null 2>&1; then
    icpx --version | head -n 1
else
    echo "NOT FOUND"
fi

echo -n "Intel Fortran Compiler (ifx): "
if command -v ifx >/dev/null 2>&1; then
    ifx --version | head -n 1
else
    echo "NOT FOUND"
fi

echo -n "Intel MPI C Compiler (mpiicpx): "
if command -v mpiicpx >/dev/null 2>&1; then
    mpiicpx --version | head -n 1
else
    echo "NOT FOUND"
fi

echo -n "Intel MPI Fortran Compiler (mpiifx): "
if command -v mpiifx >/dev/null 2>&1; then
    mpiifx --version | head -n 1
else
    echo "NOT FOUND"
fi

# Check MKL
echo -n "Intel MKL: "
if [ -d "/opt/intel/oneapi/mkl/latest" ]; then
    echo "INSTALLED at /opt/intel/oneapi/mkl/latest"
    echo "  MKL include: $(ls /opt/intel/oneapi/mkl/latest/include/ | head -n 5)"
else
    echo "NOT FOUND"
fi

# Test simple compilation
echo -e "\n=== Testing Intel Compilers ==="
cd /tmp
cat > test_intel.cpp << 'EOF'
#include <iostream>
int main() {
    std::cout << "Intel C++ compiler works!" << std::endl;
    return 0;
}
EOF

if icpx test_intel.cpp -o test_intel 2>/dev/null; then
    ./test_intel
    rm -f test_intel test_intel.cpp
    echo "✓ Intel C++ compiler: PASS"
else
    echo "✗ Intel C++ compiler: FAIL"
fi
```

### 3. Install Basic Dependencies

```bash
sudo apt update
sudo apt install -y cmake python3-dev python3-pip python3-venv git

# Create Python virtual environment (Ubuntu 23.04+ requires this)
python3 -m venv ~/venv
source ~/venv/bin/activate
pip install numpy pytest pybind11 mpi4py scipy matplotlib
```

**Verification:**

```bash
echo "=== Basic Dependencies Check ==="

# Check CMake
echo -n "CMake: "
if command -v cmake >/dev/null 2>&1; then
    cmake --version | head -n 1
else
    echo "NOT FOUND"
fi

# Check Python
echo -n "Python3: "
if command -v python3 >/dev/null 2>&1; then
    python3 --version
else
    echo "NOT FOUND"
fi

# Check Virtual Environment
echo -n "Python Venv: "
if [ -f "$HOME/venv/bin/activate" ]; then
    echo "INSTALLED at ~/venv"
else
    echo "NOT FOUND"
fi

# Check Python packages in venv
source ~/venv/bin/activate
echo -e "\nPython Packages:"
for pkg in numpy pytest pybind11 mpi4py scipy matplotlib; do
    echo -n "  $pkg: "
    python -c "import $pkg; print($pkg.__version__)" 2>/dev/null && echo "OK" || echo "NOT INSTALLED"
done

# Test numpy
echo -e "\n=== Testing NumPy ==="
python -c "import numpy as np; print(f'NumPy version: {np.__version__}'); print(f'Test array: {np.array([1,2,3])}')"

# Test MPI with Python
echo -e "\n=== Testing mpi4py ==="
python -c "from mpi4py import MPI; print(f'MPI version: {MPI.Get_version()}')"
```

### 4. Install GCC (Required for ABACUS)

**IMPORTANT**: Install GCC BEFORE loading OneAPI environment variables.

```bash
# Clear any existing compiler variables
export CC= export CXX= export FC= export LIBS= export CFLAGS=

# Download and compile GCC (version 14.1.0 recommended)
wget https://mirror.linux-ia64.org/gnu/gcc/releases/gcc-14.1.0/gcc-14.1.0.tar.xz
tar -xvf gcc-14.1.0.tar.xz
cd gcc-14.1.0
./contrib/download_prerequisites
cd ..
mkdir gcc-14.1.0-build && cd gcc-14.1.0-build
../gcc-14.1.0/configure --prefix=$HOME/software/gcc-14.1.0 --disable-multilib
make -j $(nproc)
make install

# Add to ~/.bashrc
export GCC_HOME=$HOME/software/gcc-14.1.0
echo "export GCC_HOME=$GCC_HOME" >> ~/.bashrc
echo "export PATH=\$GCC_HOME/bin:\$PATH" >> ~/.bashrc
echo "export LD_LIBRARY_PATH=\$GCC_HOME/lib:\$GCC_HOME/lib64:\$LD_LIBRARY_PATH" >> ~/.bashrc
```

**Verification:**

```bash
echo "=== GCC Installation Check ==="

# Check GCC in custom location
export GCC_HOME=$HOME/software/gcc-14.1.0
export PATH=$GCC_HOME/bin:$PATH

echo -n "GCC (custom): "
if $GCC_HOME/bin/gcc --version >/dev/null 2>&1; then
    $GCC_HOME/bin/gcc --version | head -n 1
else
    echo "NOT FOUND at $GCC_HOME"
fi

echo -n "G++ (custom): "
if $GCC_HOME/bin/g++ --version >/dev/null 2>&1; then
    $GCC_HOME/bin/g++ --version | head -n 1
else
    echo "NOT FOUND at $GCC_HOME"
fi

echo -n "GFortran (custom): "
if $GCC_HOME/bin/gfortran --version >/dev/null 2>&1; then
    $GCC_HOME/bin/gfortran --version | head -n 1
else
    echo "NOT FOUND at $GCC_HOME"
fi

# Check libraries
echo -e "\nGCC Libraries:"
for dir in lib lib64; do
    if [ -d "$GCC_HOME/$dir" ]; then
        echo "  $dir: $(ls -1 $GCC_HOME/$dir | wc -l) files found"
        echo "    Examples: $(ls -1 $GCC_HOME/$dir | head -n 5)"
    else
        echo "  $dir: NOT FOUND"
    fi
done

# Test compilation
echo -e "\n=== Testing GCC ==="
cd /tmp
cat > test_gcc.c << 'EOF'
#include <stdio.h>
int main() {
    printf("GCC works!\n");
    return 0;
}
EOF

if $GCC_HOME/bin/gcc test_gcc.c -o test_gcc 2>/dev/null; then
    ./test_gcc
    rm -f test_gcc test_gcc.c
    echo "✓ GCC C compiler: PASS"
else
    echo "✗ GCC C compiler: FAIL"
fi

# Test C++ compilation
cat > test_gcc.cpp << 'EOF'
#include <iostream>
int main() {
    std::cout << "G++ works!" << std::endl;
    return 0;
}
EOF

if $GCC_HOME/bin/g++ test_gcc.cpp -o test_gccxx 2>/dev/null; then
    ./test_gccxx
    rm -f test_gccxx test_gcc.cpp
    echo "✓ GCC C++ compiler: PASS"
else
    echo "✗ GCC C++ compiler: FAIL"
fi

# Test Fortran compilation
cat > test_gcc.f90 << 'EOF'
program test
    print *, "GFortran works!"
end program test
EOF

if $GCC_HOME/bin/gfortran test_gcc.f90 -o test_gfortran 2>/dev/null; then
    ./test_gfortran
    rm -f test_gfortran test_gcc.f90
    echo "✓ GCC Fortran compiler: PASS"
else
    echo "✗ GCC Fortran compiler: FAIL"
fi
```

### 5. Install ELPA (Required for ABACUS)

```bash
# Download ELPA
wget https://elpa.mpcdf.mpg.de/software/elpa-2025.01.001.tar.gz
tar -xzvf elpa-2025.01.001.tar.gz
cd elpa-2025.01.001
sh autogen.sh
cd ..
mkdir elpa-build && cd elpa-build

# Detect CPU architecture for optimization flags
CPU_FLAGS="-xCORE-AVX512"  # Default for Intel Xeon
if lscpu | grep -q "AMD"; then
    CPU_FLAGS="-march=znver3 -O3"  # AMD Zen3
fi

# Configure (auto-detect OneAPI paths)
ONEAPI_VERSION=$(ls /opt/intel/oneapi/ | grep -E "^[0-9]" | sort -V | tail -n 1)
MKL_HOME="/opt/intel/oneapi/mkl/$ONEAPI_VERSION"

../elpa-2025.01.001/configure \
    --prefix=$HOME/software/elpa-build \
    FC="mpiifx" FCFLAGS="-qopenmp -O3 $CPU_FLAGS" \
    CC="mpiicx" CFLAGS="-qopenmp -O3 $CPU_FLAGS" \
    --enable-openmp \
    LDFLAGS="-Wl,--copy-dt-needed-entries" \
    SCALAPACK_LDFLAGS="-L$MKL_HOME/lib/intel64 -lmkl_scalapack_lp64 -lmkl_intel_lp64 -lmkl_sequential -lmkl_core -lmkl_blacs_intelmpi_lp64 -lpthread -lm -Wl,-rpath,$MKL_HOME/lib/intel64" \
    --enable-runtime-threading-support-checks

make -j $(nproc)
make install

# Create symlink for ABACUS
ln -s $HOME/software/elpa-build/include/elpa_openmp-*/elpa $HOME/software/elpa-build/include/elpa
```

**Verification:**

```bash
echo "=== ELPA Installation Check ==="

# Check installation directory
ELPA_HOME=$HOME/software/elpa-build
if [ -d "$ELPA_HOME" ]; then
    echo "ELPA installed at: $ELPA_HOME"
    echo "  Include: $ELPA_HOME/include"
    echo "  Lib: $ELPA_HOME/lib"
    echo "  Bin: $ELPA_HOME/bin"
else
    echo "ELPA NOT FOUND at $ELPA_HOME"
fi

# Check ELPA symlink
if [ -L "$ELPA_HOME/include/elpa" ]; then
    echo "ELPA symlink: $ELPA_HOME/include/elpa -> $(readlink -f $ELPA_HOME/include/elpa)"
else
    echo "WARNING: ELPA symlink NOT FOUND at $ELPA_HOME/include/elpa"
fi

# Check ELPA libraries
echo -e "\nELPA Libraries:"
if [ -d "$ELPA_HOME/lib" ]; then
    find $ELPA_HOME/lib -name "libelpa*" -type f 2>/dev/null | head -n 10
fi

# Check ELPA modules
echo -e "\nELPA Modules:"
if [ -d "$ELPA_HOME/include" ]; then
    find $ELPA_HOME/include -name "*.mod" -type f 2>/dev/null | head -n 10
fi

# Test ELPA with a simple program (if tests are available)
if [ -f "$ELPA_HOME/bin/elpa_1stage_real_test" ]; then
    echo -e "\n✓ ELPA test executables found"
else
    echo -e "\n⚠ ELPA test executables not found (may not be installed)"
fi
```

### 6. Install LibXC (Required for ABACUS)

```bash
wget https://libxc.gitlab.io/download/libxc-6.2.2.tar.bz2
tar -xjvf libxc-6.2.2.tar.bz2
cd libxc-6.2.2/
cmake -H. -Bobjdir -DCMAKE_C_COMPILER=mpiicx -DCMAKE_INSTALL_PREFIX=$HOME/software/libxc-6.2.2
cd objdir && make -j $(nproc)
make install
```

**Verification:**

```bash
echo "=== LibXC Installation Check ==="

LIBXC_HOME=$HOME/software/libxc-6.2.2
if [ -d "$LIBXC_HOME" ]; then
    echo "LibXC installed at: $LIBXC_HOME"
else
    echo "LibXC NOT FOUND at $LIBXC_HOME"
fi

# Check CMake config files (crucial for ABACUS)
echo -e "\nLibXC CMake Config:"
if [ -f "$LIBXC_HOME/share/cmake/Libxc/LibxcConfig.cmake" ]; then
    echo "✓ LibxcConfig.cmake found at $LIBXC_HOME/share/cmake/Libxc/"
    ls -la $LIBXC_HOME/share/cmake/Libxc/ | head -n 10
else
    echo "✗ LibxcConfig.cmake NOT FOUND - ABACUS will fail to find LibXC!"
fi

# Check pkg-config
echo -e "\nLibXC pkg-config:"
if command -v pkg-config >/dev/null 2>&1; then
    pkg-config --modversion libxc 2>/dev/null || echo "libxc not in pkg-config path"
else
    echo "pkg-config not available"
fi

# Check libraries
echo -e "\nLibXC Libraries:"
if [ -d "$LIBXC_HOME/lib" ]; then
    find $LIBXC_HOME/lib -name "libxc*" -type f 2>/dev/null
fi

# Check headers
echo -e "\nLibXC Headers:"
if [ -d "$LIBXC_HOME/include" ]; then
    ls -1 $LIBXC_HOME/include/xc*.h 2>/dev/null | head -n 10
fi
```

### 7. Install LibRPA

```bash
# Clone repository
git clone -b qsgw git@github.com:bhjia-phys/LibRPA.git $HOME/LibRPA
cd $HOME/LibRPA

# Update thirdparty submodules
cd thirdparty/LibComm
git submodule init
git submodule update --recursive

# Fix known bug in LibRI
sed -i 's/this->period/this->lri.period/g' $HOME/LibRPA/thirdparty/LibRI/include/RI/physics/RPA.hpp

# Configure cmake.inc (auto-detect OneAPI version)
cat > cmake.inc << EOF
set(CMAKE_CXX_COMPILER "mpiicpx" CACHE STRING "" FORCE)
set(CMAKE_Fortran_COMPILER "ifx" CACHE STRING "" FORCE)
EOF

# Build
cd $HOME/LibRPA
cmake -B build_test
cmake --build build_test -j $(nproc)
```

**Verification:**

```bash
echo "=== LibRPA Installation Check ==="

LIBRPA_HOME=$HOME/LibRPA
if [ -d "$LIBRPA_HOME" ]; then
    echo "LibRPA installed at: $LIBRPA_HOME"
else
    echo "LibRPA NOT FOUND at $LIBRPA_HOME"
fi

# Check build directory
if [ -d "$LIBRPA_HOME/build_test" ]; then
    echo "✓ LibRPA build directory exists"
    echo "  Executables in build_test/bin:"
    find $LIBRPA_HOME/build_test/bin -type f -executable 2>/dev/null | head -n 10
else
    echo "✗ LibRPA build directory NOT FOUND"
fi

# Check thirdparty dependencies
echo -e "\nLibRPA Thirdparty Dependencies:"
for dep in cereal-1.3.2 LibComm LibRI; do
    if [ -d "$LIBRPA_HOME/thirdparty/$dep" ]; then
        echo "  ✓ $dep"
    else
        echo "  ✗ $dep NOT FOUND"
    fi
done

# Check for LibRI bug fix
echo -e "\nLibRI Bug Fix Check:"
if grep -q "this->lri.period" $LIBRPA_HOME/thirdparty/LibRI/include/RI/physics/RPA.hpp 2>/dev/null; then
    echo "✓ LibRI period bug fix applied"
else
    echo "⚠ LibRI period bug fix may NOT be applied"
fi
```

### 8. Install FHI-aims

```bash
# Clone FHI-aims (requires access credentials)
git clone <your-fhi-aims-repo> $HOME/FHI-aims
cd $HOME/FHI-aims

# Create initial_cache.cmake
ONEAPI_VERSION=$(ls /opt/intel/oneapi/ | grep -E "^[0-9]" | sort -V | tail -n 1)
cat > initial_cache.cmake << EOF
set(USE_GREENX ON CACHE BOOL "" FORCE)
set(LIB_PATHS "/opt/intel/oneapi/mkl/$ONEAPI_VERSION/lib/intel64/" CACHE STRING "" FORCE)
set(CMAKE_CXX_COMPILER "icpx" CACHE STRING "" FORCE)
set(CMAKE_C_COMPILER "icx" CACHE STRING "" FORCE)
set(CMAKE_Fortran_COMPILER "ifx" CACHE STRING "" FORCE)
EOF

# Build
cmake -B build_test -C initial_cache.cmake
cmake --build build_test -j $(nproc)
```

### 9. Install PYATB

```bash
# Install Eigen3
wget https://gitlab.com/libeigen/eigen/-/archive/3.4.0/eigen-3.4.0.tar.bz2
tar xvf eigen-3.4.0.tar.bz2
mkdir eigen-build && cd eigen-3.4.0/build
cmake .. -DCMAKE_INSTALL_PREFIX=$HOME/eigen-3.4.0
make install

# Clone PYATB
git clone -b enable_head_wing git@github.com:AroundPeking/pyatb.git $HOME/pyatb
cd $HOME/pyatb

# Create siteconfig.py
ONEAPI_VERSION=$(ls /opt/intel/oneapi/ | grep -E "^[0-9]" | sort -V | tail -n 1)
cat > siteconfig.py << EOF
compiler = 'icpx'
mkl_include_dir = '/opt/intel/oneapi/mkl/$ONEAPI_VERSION/include'
mkl_library_dir = '/opt/intel/oneapi/mkl/$ONEAPI_VERSION/lib'
eigen_include_dir = '$HOME/eigen-3.4.0/include/eigen3'
EOF

# Fix setup.py (icpc -> icpx)
sed -i 's/icpc/icpx/g' setup.py

# Install
pip install ./
```

**Verification:**

```bash
echo "=== PYATB Installation Check ==="

# Check Eigen3
EIGEN_HOME=$HOME/eigen-3.4.0
if [ -d "$EIGEN_HOME/include/eigen3" ]; then
    echo "✓ Eigen3 installed at: $EIGEN_HOME"
    echo "  Eigen headers: $(ls -1 $EIGEN_HOME/include/eigen3/ | head -n 10)"
else
    echo "✗ Eigen3 NOT FOUND at $EIGEN_HOME"
fi

# Check PYATB installation
echo -e "\nPYATB Python Module:"
python -c "import pyatb; print(f'PYATB version: {pyatb.__version__}'); print(f'PYATB location: {pyatb.__file__}')" 2>/dev/null || echo "PYATB NOT INSTALLED"

# Check PYATB configuration
echo -e "\nPYATB Configuration:"
if [ -f "$HOME/pyatb/siteconfig.py" ]; then
    echo "✓ siteconfig.py found"
    cat $HOME/pyatb/siteconfig.py
else
    echo "⚠ siteconfig.py not found in $HOME/pyatb/"
fi
```

### 10. Install ABACUS

```bash
# Clone ABACUS
git clone https://github.com/deepmodeling/abacus-develop.git $HOME/abacus-develop
cd $HOME/abacus-develop

# Modify CMakeLists.txt with paths
cat >> CMakeLists.txt << EOF

# DFT Stack Installation Paths
set(CEREAL_DIR "$HOME/LibRPA/thirdparty/cereal-1.3.2" CACHE STRING "")
set(CEREAL_INCLUDE_DIR "$HOME/LibRPA/thirdparty/cereal-1.3.2/include" CACHE STRING "")
set(ELPA_DIR "$HOME/software/elpa-build" CACHE STRING "")
set(LIBRI_DIR "$HOME/LibRPA/thirdparty/LibRI" CACHE STRING "")
set(LIBCOMM_DIR "$HOME/LibRPA/thirdparty/LibComm" CACHE STRING "")
set(Libxc_DIR "$HOME/software/libxc-6.2.2" CACHE STRING "")
EOF

# Build
cmake -B build_test
cmake --build build_test -j $(nproc)
cmake --install build_test
```

**Verification:**

```bash
echo "=== ABACUS Installation Check ==="

ABACUS_HOME=$HOME/abacus-develop
if [ -d "$ABACUS_HOME" ]; then
    echo "ABACUS source at: $ABACUS_HOME"
else
    echo "ABACUS source NOT FOUND at $ABACUS_HOME"
fi

# Check ABACUS build
if [ -d "$ABACUS_HOME/build_test" ]; then
    echo "✓ ABACUS build directory exists"
    echo "  ABACUS executable:"
    find $ABACUS_HOME/build_test -name "abacus" -type f -executable 2>/dev/null
else
    echo "✗ ABACUS build directory NOT FOUND"
fi

# Check ABACUS version
if [ -f "$ABACUS_HOME/build_test/abacus" ]; then
    echo -e "\n✓ ABACUS executable found"
    $ABACUS_HOME/build_test/abacus --version 2>/dev/null || echo "  (version info not available)"
fi

# Check installed ABACUS
if command -v abacus >/dev/null 2>&1; then
    echo -e "\n✓ ABACUS installed in system PATH"
    which abacus
    abacus --version 2>/dev/null || echo "  (version info not available)"
else
    echo -e "\n⚠ ABACUS not in system PATH (may need to add to PATH)"
fi
```

## Final Comprehensive Verification

After all installations are complete, run this comprehensive verification:

```bash
echo "=========================================="
echo "  DFT Stack Installation Final Report"
echo "=========================================="
echo ""

# OneAPI
echo "1. OneAPI (Intel Compilers)"
source /opt/intel/oneapi/setvars.sh > /dev/null 2>&1
if command -v icpx >/dev/null 2>&1; then
    echo "   ✓ Intel C++ (icpx): $(icpx --version | head -n 1)"
else
    echo "   ✗ Intel C++ (icpx): NOT FOUND"
fi
if command -v ifx >/dev/null 2>&1; then
    echo "   ✓ Intel Fortran (ifx): $(ifx --version | head -n 1)"
else
    echo "   ✗ Intel Fortran (ifx): NOT FOUND"
fi
echo ""

# GCC
echo "2. GCC (Custom Build)"
export GCC_HOME=$HOME/software/gcc-14.1.0
if [ -f "$GCC_HOME/bin/gcc" ]; then
    echo "   ✓ GCC: $($GCC_HOME/bin/gcc --version | head -n 1)"
else
    echo "   ✗ GCC: NOT FOUND"
fi
echo ""

# Python Environment
echo "3. Python Environment"
if [ -f "$HOME/venv/bin/python" ]; then
    source ~/venv/bin/activate
    echo "   ✓ Python: $(python --version)"
    echo "   ✓ NumPy: $(python -c 'import numpy; print(numpy.__version__)' 2>/dev/null || echo 'N/A')"
    echo "   ✓ SciPy: $(python -c 'import scipy; print(scipy.__version__)' 2>/dev/null || echo 'N/A')"
    echo "   ✓ mpi4py: $(python -c 'import mpi4py; print(mpi4py.__version__)' 2>/dev/null || echo 'N/A')"
else
    echo "   ✗ Python venv: NOT FOUND"
fi
echo ""

# ELPA
echo "4. ELPA"
if [ -d "$HOME/software/elpa-build" ]; then
    echo "   ✓ ELPA installed at $HOME/software/elpa-build"
    if [ -L "$HOME/software/elpa-build/include/elpa" ]; then
        echo "   ✓ ELPA symlink exists"
    else
        echo "   ✗ ELPA symlink missing"
    fi
else
    echo "   ✗ ELPA: NOT FOUND"
fi
echo ""

# LibXC
echo "5. LibXC"
if [ -f "$HOME/software/libxc-6.2.2/share/cmake/Libxc/LibxcConfig.cmake" ]; then
    echo "   ✓ LibXC installed (CMake config found)"
else
    echo "   ✗ LibXC CMake config: NOT FOUND"
fi
echo ""

# LibRPA
echo "6. LibRPA"
if [ -d "$HOME/LibRPA/build_test" ]; then
    echo "   ✓ LibRPA build exists"
    if find $HOME/LibRPA/build_test/bin -type f -executable | grep -q .; then
        echo "   ✓ LibRPA executables found"
    else
        echo "   ✗ LibRPA executables: NOT FOUND"
    fi
else
    echo "   ✗ LibRPA: NOT FOUND"
fi
echo ""

# FHI-aims
echo "7. FHI-aims"
if [ -d "$HOME/FHI-aims" ]; then
    echo "   ✓ FHI-aims directory exists"
    if find $HOME/FHI-aims/build_test -type f -executable | grep -q .; then
        echo "   ✓ FHI-aims executables found"
    else
        echo "   ⚠ FHI-aims executables: Check build status"
    fi
else
    echo "   ✗ FHI-aims: NOT FOUND (requires license)"
fi
echo ""

# PYATB
echo "8. PYATB"
if python -c "import pyatb" 2>/dev/null; then
    echo "   ✓ PYATB installed: $(python -c 'import pyatb; print(pyatb.__version__)' 2>/dev/null || echo 'N/A')"
else
    echo "   ✗ PYATB: NOT INSTALLED"
fi
echo ""

# ABACUS
echo "9. ABACUS"
if [ -f "$HOME/abacus-develop/build_test/abacus" ]; then
    echo "   ✓ ABACUS executable exists"
    $HOME/abacus-develop/build_test/abacus --version 2>/dev/null | head -n 1 || echo "   (version info not available)"
elif command -v abacus >/dev/null 2>&1; then
    echo "   ✓ ABACUS in PATH: $(which abacus)"
else
    echo "   ✗ ABACUS: NOT FOUND"
fi
echo ""

# Environment Variables
echo "10. Environment Variables (.bashrc)"
if grep -q "oneapi/setvars.sh" ~/.bashrc 2>/dev/null; then
    echo "   ✓ OneAPI sourced"
else
    echo "   ✗ OneAPI not sourced in .bashrc"
fi
if grep -q "GCC_HOME" ~/.bashrc 2>/dev/null; then
    echo "   ✓ GCC_HOME set"
else
    echo "   ✗ GCC_HOME not set in .bashrc"
fi
if grep -q "venv/bin/activate" ~/.bashrc 2>/dev/null; then
    echo "   ✓ Python venv activated"
else
    echo "   ✗ Python venv not activated in .bashrc"
fi
echo ""

# Disk Usage
echo "11. Disk Usage"
echo "   Software directory:"
du -sh $HOME/software 2>/dev/null || echo "   Not found"
echo "   LibRPA directory:"
du -sh $HOME/LibRPA 2>/dev/null || echo "   Not found"
echo ""

echo "=========================================="
echo "  Installation report complete!"
echo "=========================================="
```

## Server-Specific Adjustments

### Architecture Detection

The skill automatically detects CPU architecture and sets appropriate optimization flags:

```bash
# Detect CPU vendor and model
CPU_INFO=$(lscpu | grep "Model name")

# Set optimization flags based on CPU
if echo "$CPU_INFO" | grep -q "Intel.*Xeon.*[Ss]kylake"; then
    CPU_FLAGS="-xCORE-AVX512"
elif echo "$CPU_INFO" | grep -q "Intel.*Xeon.*[Cc]ascadelake"; then
    CPU_FLAGS="-xCASCADELAKE"
elif echo "$CPU_INFO" | grep -q "AMD"; then
    CPU_FLAGS="-march=znver3 -O3"
else
    CPU_FLAGS="-march=native -O3"
fi
```

### OneAPI Version Handling

For different OneAPI versions (2024.x, 2025.x), compiler names differ:

| Version | Old Compiler | New Compiler |
|---------|--------------|--------------|
| 2023 and earlier | icpc, icc, ifort | - |
| 2024 and later | - | icpx, icx, ifx |
| MPI (old) | mpiicpc, mpiifort | - |
| MPI (new) | mpiicpx, mpiifx | - |

```bash
# Auto-detect and set compiler commands
ONEAPI_YEAR=$(ls /opt/intel/oneapi/ 2>/dev/null | grep -E "^[0-9]" | cut -d'.' -f1 | sort -V | tail -n 1)
if [ "$ONEAPI_YEAR" -ge 2024 ]; then
    CXX_COMP="icpx"
    C_COMP="icx"
    F_COMP="ifx"
    MPI_CXX_COMP="mpiicpx"
    MPI_F_COMP="mpiifx"
else
    CXX_COMP="icpc"
    C_COMP="icc"
    F_COMP="ifort"
    MPI_CXX_COMP="mpiicpc"
    MPI_F_COMP="mpiifort"
fi
```

## Environment Variables

Add these to `~/.bashrc`:

```bash
# OneAPI
source /opt/intel/oneapi/setvars.sh > /dev/null

# GCC (if custom installed)
export GCC_HOME=$HOME/software/gcc-14.1.0
export PATH=$GCC_HOME/bin:$PATH
export LD_LIBRARY_PATH=$GCC_HOME/lib:$GCC_HOME/lib64:$LD_LIBRARY_PATH

# Python virtual environment
source ~/venv/bin/activate

# MKL (if needed)
export MKL_HOME=/opt/intel/oneapi/mkl/latest
export LD_LIBRARY_PATH=$MKL_HOME/lib/intel64:$LD_LIBRARY_PATH
```

## Important Notes

- **Installation Order**: Follow the order above (OneAPI → GCC → ELPA → LibXC → LibRPA → FHI-aims → PYATB → ABACUS)
- **GCC Before OneAPI**: Always install GCC before loading OneAPI environment variables
- **SSH Keys**: Configure SSH keys for GitHub access before cloning repositories
- **Disk Space**: Full installation requires ~50GB of disk space
- **Compilation Time**: Full compilation can take several hours depending on CPU
- **FHI-aims Access**: FHI-aims requires license; contact FHI-aims team for access
- **Version Compatibility**: Use compatible versions (ELPA 2025.01, LibXC 6.2.2, GCC 14.1.0)
- **CPU Optimization**: Optimization flags are auto-detected based on CPU architecture
- **OneAPI Versions**: Script auto-detects OneAPI version and uses correct compiler names

## Quick Start Example

```bash
User: /gw-toolchain login@server.example.com

[AI Response]:
1. Connecting to server...
2. Detecting environment: Intel Xeon Gold 6348, OneAPI 2025.1 installed
3. Installing dependencies...
4. Installing ELPA...
5. Installing LibXC...
6. Installing LibRPA...
7. Installing PYATB...
8. Installing ABACUS...
9. Done! Installation complete at /home/login/software/
```
