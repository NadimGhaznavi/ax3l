---
title: Qwen 3.5 Model Setup
author_profile: true
layout: single
---

![Ax3l]({{ '/pages/images/ax3l.png' | relative_url }})

## Create a virtual environment

```sh
python3 -m venv venv
. venv/bin/activate
```

## Install the Python requirements

From within the virtual environment, install the llama.cpp conversion-script
requirements:

```sh
cd /opt/dev/llama.cpp
pip install -r requirements.txt
```

## Download the model

```sh
git lfs install
cd /opt/dev
git clone --depth 1 https://huggingface.co/Qwen/Qwen3.5-4B
```

The download is approximately 18 GB and may take a while. Verify the checkout:

```sh
# cd Qwen3.5-4B
# git status
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean

$ git lfs ls-files
26a93f066e * model.safetensors-00001-of-00002.safetensors
cb544bd9bf * model.safetensors-00002-of-00002.safetensors
5f9e4d4901 * tokenizer.json

$ git rev-parse HEAD
851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a
```

## Convert the language model to GGUF

Qwen 3.5 4B supports vision. In llama.cpp, the language model and vision
encoder/projector are exported as separate GGUF files. Both must be loaded
to accept images.

```sh
cd /opt/dev/llama.cpp
mkdir -p /opt/dev/models/intermediate /opt/dev/models/quantized

python convert_hf_to_gguf.py \
    /opt/dev/Qwen3.5-4B \
    --outfile /opt/dev/models/intermediate/Qwen3.5-4B-BF16.gguf \
    --outtype bf16

...
INFO:hf-to-gguf:Model successfully exported to /opt/dev/models/intermediate/Qwen3.5-4B-BF16.gguf
```

## Convert the vision/multimodal projector

Use the same source model to export the vision component in F16:

```sh
cd /opt/dev/llama.cpp
python convert_hf_to_gguf.py \
    /opt/dev/Qwen3.5-4B \
    --mmproj \
    --outfile /opt/dev/models/intermediate/mmproj-Qwen3.5-4B-F16.gguf \
    --outtype f16
```

## Quantize only the language model

Keep the vision projector in F16; quantize the language model to Q4_K_M:

```sh
./build/bin/llama-quantize \
    /opt/dev/models/intermediate/Qwen3.5-4B-BF16.gguf \
    /opt/dev/models/quantized/Qwen3.5-4B-Q4_K_M.gguf \
    Q4_K_M
```

## Install the model and vision projector

```sh
cp /opt/dev/models/quantized/Qwen3.5-4B-Q4_K_M.gguf /opt/prod/models/
cp /opt/dev/models/intermediate/mmproj-Qwen3.5-4B-F16.gguf /opt/prod/models/
```

## Run with vision support

Load both files with llama-server:

```sh
/opt/prod/llama.cpp/bin/llama-server \
    --model /opt/prod/models/Qwen3.5-4B-Q4_K_M.gguf \
    --mmproj /opt/prod/models/mmproj-Qwen3.5-4B-F16.gguf \
    -c 12288 \
    --host 0.0.0.0 \
    --port 27770 \
    --metrics \
    --jinja
```

For a systemd deployment, include the same `--mmproj` argument in the
service's `ExecStart` command. Ax3l's `scripts/install-services.sh -env prod`
includes this argument for Qwen 3.5 and requires the projector file above
before installing the service. Stop the existing service before
running the standalone command above to avoid a port conflict.

After starting the server, check its advertised capabilities:

```sh
curl -fsS http://127.0.0.1:27770/props
```

The response should contain `"vision": true` inside `modalities`. Refresh the
web client so it picks up the updated capabilities and allows image uploads.
Loading only the language-model GGUF leaves vision disabled.

See llama.cpp's [multimodal documentation](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md)
for the model and projector loading options.

---

[Back](/pages/env-setup)
