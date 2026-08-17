# WHP PowerPC LLVM/LLD installs are intentionally rooted at <prefix>/lib.
# Load this through CMAKE_PROJECT_TOP_LEVEL_INCLUDES to shadow any stale
# build-machine GNUInstallDirs cache value without changing LLVM's ABI layout.
set(CMAKE_INSTALL_LIBDIR "lib" CACHE PATH "PowerPC LLVM library install directory" FORCE)
