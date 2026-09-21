# Local Cache Policy

Core Equity keeps rebuildable caches on `D:\ai-cache` to protect the Windows system disk.

Configured Windows user environment variables:

- `HF_HOME=D:\ai-cache\huggingface`
- `HUGGINGFACE_HUB_CACHE=D:\ai-cache\huggingface\hub`
- `TRANSFORMERS_CACHE=D:\ai-cache\huggingface\transformers`
- `PIP_CACHE_DIR=D:\ai-cache\pip`
- `UV_CACHE_DIR=D:\ai-cache\uv`
- `TORCH_HOME=D:\ai-cache\torch`
- `npm_config_cache=D:\ai-cache\npm`
- `PLAYWRIGHT_BROWSERS_PATH=D:\ai-cache\playwright`

WSL launchers should source:

```bash
source /mnt/d/trading-agent/configs/cache-env.sh
```

Safe cleanup candidates on `C:`:

- `C:\Users\cheur\AppData\Local\Temp`
- `C:\Windows\Temp`
- `C:\Users\cheur\AppData\Local\pip\Cache`
- `C:\Users\cheur\AppData\Local\uv\cache`
- `C:\Users\cheur\AppData\Local\NVIDIA\DXCache`
- `C:\Users\cheur\AppData\Local\NVIDIA\GLCache`
- `C:\Users\cheur\AppData\Local\NVIDIA\ComputeCache`

Do not delete without review:

- `C:\Users\cheur\AppData\Local\wsl`
- `C:\Users\cheur\.cache\huggingface`
- Browser/wallet data such as Brave, MetaMask, Rabby or Phantom profiles.
