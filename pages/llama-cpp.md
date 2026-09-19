---
title: Llama CPP Setup
author_profile: true
layout: single
---


## Download llama.cpp

```sh
git clone https://github.com/ggml-org/llama.cpp
```

## Build llama.cpp with CUDA support

```sh
cd llama.cpp
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON
cmake --build build --config Release -j 11
cmake --install build --prefix /opt/prod/llama.cpp-0.4.0
```

Add the library search path to the system. **As root**:

```sh
echo '/opt/prod/llama.cpp-0.4.0/lib' > /etc/ld.so.conf.d/llama.cpp.conf
ldconfig
```

---

[Back](/env-setup)