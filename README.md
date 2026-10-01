# 🎬 Auto Video Creator — Meta + Vibes + Fish Audio

Sistema híbrido (GitHub Actions cloud + PC local com GPU) que gera vídeos MP4 automaticamente.

## Como usar

1. Vá em **Actions** no GitHub → **🎬 Gerar Vídeo Automático** → **Run workflow**
2. Preencha o tema, duração e estilo
3. Aguarde — o vídeo final estará em **Artifacts** ao finalizar

## Fluxo

```
[Cloud] OpenRouter → roteiro.json
[Cloud] Fish Audio → audio_cena_NN.mp3
[Local] Playwright → Meta.ai → imagem_cena_NN.png
[Local] Playwright → Vibes.ai → video_cena_NN.mp4
[Local] FFmpeg GPU → output/video_final.mp4
```

## Secrets necessários no GitHub

| Secret | Valor |
|---|---|
| `OPENROUTER_API_KEY` | `sk-or-v1-...` |
| `FISH_API_KEY` | `sk-fish-...` |
| `CHROME_USER_DATA_DIR` | `C:\Users\robso\AppData\Local\Google\Chrome\User Data` |
| `META_DOWNLOAD_DIR` | `C:\Users\robso\Downloads\meta-folder-1` |
| `VIBES_DOWNLOAD_DIR` | `C:\Users\robso\Downloads\vibes-folder-1` |

## Self-Hosted Runner

Configure o runner local em: **GitHub → Settings → Actions → Runners**

Label obrigatório: `gpu`

## Configurar música de fundo

Coloque um arquivo `music/background.mp3` no projeto.
