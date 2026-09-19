---
title: Phi Model Setup
author_profile: true
layout: single
---

![Ax3l]({{ '/pages/images/ax3l.png' | relative_url }})

## Set Up Hugging Face Access

**As root**:

```sh
cd /opt/dev
python3 -m venv huggingface-venv
source ./huggingface-venv/bin/activate
pip install --upgrade pip
pip install huggingface_hub
cd /opt/src/llama.cpp
pip install -r requirements.txt
```

## Download Phi

This is **BIG**, so it will take a while.

```sh
hf download microsoft/Phi-4-mini-instruct \
    --local-dir /opt/dev/Phi-4-mini-instruct
```