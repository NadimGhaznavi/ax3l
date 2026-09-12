---
title: Qwen Model Setup
author_profile: true
layout: single
---

![Ax3l]({{ '/pages/images/ax3l.png' | relative_url }})

# Download the model

```sh
cd /opt/dev

source /opt/dev/huggingface-venv/bin/activate

hf download Qwen/Qwen2.5-VL-3B-Instruct \
    --local-dir /opt/dev/Qwen2.5-VL-3B-Instruct
```

# Convert to F16

```sh
cd /opt/src/llama.cpp
python3 convert_hf_to_gguf.py \
    /opt/dev/Qwen2.5-VL-3B-Instruct \
    --outfile /opt/dev/Qwen2.5-VL-3B-Instruct/Qwen2.5-VL-3B-Instruct-F16.gguf \
    --outtype f16
```

# Convert the vision/multimodal projector

```sh
cd /opt/src/llama.cpp
python3 convert_hf_to_gguf.py \
    /opt/dev/Qwen2.5-VL-3B-Instruct \
    --mmproj \
    --outfile /opt/dev/Qwen2.5-VL-3B-Instruct/mmproj-Qwen2.5-VL-3B-Instruct-F16.gguf \
    --outtype f16
```

# Quantize only the Language Model

```sh
/opt/prod/llama.cpp-0.4.0/bin/llama-quantize \
    /opt/dev/Qwen2.5-VL-3B-Instruct/Qwen2.5-VL-3B-Instruct-F16.gguf \
    /opt/dev/Qwen2.5-VL-3B-Instruct/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf \
    Q4_K_M
```

# Final Build

```sh
/opt/prod/llama.cpp-0.4.0/bin/llama-server \
    -m /opt/dev/Qwen2.5-VL-3B-Instruct/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf \
    --mmproj /opt/dev/Qwen2.5-VL-3B-Instruct/mmproj-Qwen2.5-VL-3B-Instruct-F16.gguf \
    -c 4096
```