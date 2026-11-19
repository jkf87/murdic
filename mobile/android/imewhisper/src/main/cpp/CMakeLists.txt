# IME 전용 whisper.cpp JNI 라이브러리.
# whisper.rn의 .so는 심볼을 숨기고(JSI 전용) 빌드되므로 IME(Kotlin 서비스)에서 부를 수 없다.
# 같은 whisper.rn 패키지의 cpp/ 소스를 그대로 써서 버전을 하나로 유지한다.
cmake_minimum_required(VERSION 3.22)
project(murdicwhisper C CXX)

set(CMAKE_CXX_STANDARD 17)
set(W ${CMAKE_SOURCE_DIR}/../../../../../node_modules/whisper.rn/cpp)

include_directories(${W} ${W}/ggml-cpu)

set(SOURCES
    ${W}/ggml.c
    ${W}/ggml.cpp
    ${W}/ggml-alloc.c
    ${W}/ggml-backend.cpp
    ${W}/ggml-backend-meta.cpp
    ${W}/ggml-backend-reg.cpp
    ${W}/ggml-backend-dl.cpp
    ${W}/ggml-cpu/amx/amx.cpp
    ${W}/ggml-cpu/amx/mmq.cpp
    ${W}/ggml-cpu/ggml-cpu.c
    ${W}/ggml-cpu/ggml-cpu.cpp
    ${W}/ggml-cpu/quants.c
    ${W}/ggml-cpu/traits.cpp
    ${W}/ggml-cpu/repack.cpp
    ${W}/ggml-cpu/unary-ops.cpp
    ${W}/ggml-cpu/binary-ops.cpp
    ${W}/ggml-cpu/vec.cpp
    ${W}/ggml-cpu/ops.cpp
    ${W}/ggml-opt.cpp
    ${W}/ggml-threading.cpp
    ${W}/ggml-quants.c
    ${W}/gguf.cpp
    ${W}/whisper.cpp
    ${CMAKE_SOURCE_DIR}/murdic_whisper.cpp
)

find_library(LOG_LIB log)

function(build_library name arch flags)
    set(ARCH_SOURCES "")
    if (NOT ${arch} STREQUAL "generic")
        set(ARCH_SOURCES ${W}/ggml-cpu/arch/${arch}/quants.c ${W}/ggml-cpu/arch/${arch}/repack.cpp)
    endif ()
    add_library(${name} SHARED ${SOURCES} ${ARCH_SOURCES})
    target_link_libraries(${name} ${LOG_LIB} android)
    if (${arch} STREQUAL "generic")
        target_compile_options(${name} PRIVATE -DWSP_GGML_CPU_GENERIC)
    endif ()
    target_compile_definitions(${name} PRIVATE _GNU_SOURCE)
    separate_arguments(FLAG_LIST UNIX_COMMAND "${flags}")
    target_compile_options(${name} PRIVATE -DWSP_GGML_USE_CPU -DWSP_GGML_USE_CPU_REPACK -pthread ${FLAG_LIST}
        -O3 -DNDEBUG -fvisibility=hidden -fvisibility-inlines-hidden -ffunction-sections -fdata-sections)
    target_link_options(${name} PRIVATE -Wl,--gc-sections -Wl,--exclude-libs,ALL)
endfunction()

if (${ANDROID_ABI} STREQUAL "arm64-v8a")
    build_library(murdicwhisper_v8fp16 "arm" "-march=armv8.2-a+fp16")
    build_library(murdicwhisper_v8 "arm" "-march=armv8-a")
elseif (${ANDROID_ABI} STREQUAL "x86_64")
    build_library(murdicwhisper_x86_64 "x86" "-march=x86-64 -mtune=intel -msse4.2 -mpopcnt")
else ()
    build_library(murdicwhisper "generic" "")
endif ()
