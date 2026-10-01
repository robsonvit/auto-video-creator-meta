"""
04_automacao_vibes.py
──────────────────────
Automatiza a geração e download de vídeos no Vibes.ai
usando a extensão "Vibes Automation" já instalada no Chrome.

Para cada imagem gerada pelo Meta.ai, anima ela no Vibes.ai
usando o modo "Frame to Video", gerando clips de 5 segundos.

Entrada:  temp/roteiro.json + temp/imagem_cena_NN.png
Saída:    temp/video_cena_01.mp4, video_cena_02.mp4, ...
"""

import os
import json
import sys
import time
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ── Configurações ─────────────────────────────────────────────────────────────
CHROME_USER_DATA = os.environ.get(
    "CHROME_USER_DATA_DIR",
    r"C:\Users\robso\AppData\Local\Google\Chrome\User Data"
)
CHROME_PROFILE   = os.environ.get("CHROME_PROFILE", "Default")

VIBES_DOWNLOAD_DIR = Path(os.environ.get(
    "VIBES_DOWNLOAD_DIR",
    r"C:\Users\robso\Downloads\vibes-folder-1"
))

TEMP_DIR     = Path("temp")
ROTEIRO_FILE = TEMP_DIR / "roteiro.json"

TIMEOUT_GERACAO   = 180_000   # 3 min p/ o vídeo ser gerado
DELAY_ENTRE_CENAS = 8         # segundos entre cenas


def aguardar_novo_video(pasta: Path, ts_anterior: float, timeout_s: int = 180) -> Path | None:
    """Aguarda um novo arquivo de vídeo aparecer na pasta."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        for ext in [".mp4", ".webm", ".mov"]:
            for f in pasta.glob(f"*{ext}"):
                if f.stat().st_mtime > ts_anterior:
                    time.sleep(2)  # Aguarda escrita completa
                    return f
        time.sleep(1.5)
    return None


def upload_imagem_vibes(page, imagem_path: str):
    """Faz upload de uma imagem para o Vibes.ai."""
    # Localiza a área de upload da extensão ou da interface nativa
    # A extensão "Vibes Automation" tem área de drag & drop
    
    # Tenta via input file (mais confiável)
    file_input = page.locator("input[type='file']").first
    if file_input:
        file_input.set_input_files(imagem_path)
        time.sleep(2)
        return True

    # Fallback: drag & drop na área indicada
    upload_area = page.locator(
        "[class*='upload'], [class*='drop'], [aria-label*='upload'], "
        "[aria-label*='Upload'], .upload-area, .drop-zone"
    ).first
    if upload_area:
        upload_area.set_input_files(imagem_path)
        return True

    return False


def automacao_vibes():
    roteiro = json.loads(ROTEIRO_FILE.read_text(encoding="utf-8"))
    cenas   = roteiro["cenas"]

    VIBES_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    print(f"🎬 Animando {len(cenas)} imagens no Vibes.ai (Frame to Video)...")
    print(f"   Chrome profile: {CHROME_USER_DATA}\\{CHROME_PROFILE}")
    print(f"   Download dir:   {VIBES_DOWNLOAD_DIR}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=CHROME_USER_DATA,
            channel="chrome",
            headless=False,
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                f"--profile-directory={CHROME_PROFILE}",
            ],
            accept_downloads=True,
        )

        page = context.new_page()
        page.goto("https://vibes.ai/", wait_until="domcontentloaded")
        print("   Vibes.ai carregado. Aguardando 4s para estabilizar...")
        time.sleep(4)

        for cena in cenas:
            num           = cena["numero"]
            imagem_path   = str((TEMP_DIR / f"imagem_cena_{num:02d}.png").resolve())
            prompt_mov    = cena.get("prompt_movimento", "slow gentle zoom in, cinematic motion")
            dest          = TEMP_DIR / f"video_cena_{num:02d}.mp4"

            if not Path(imagem_path).exists():
                print(f"  ⚠️  Imagem {imagem_path} não encontrada — pulando cena {num}")
                continue

            print(f"\n  → Cena {num}/{len(cenas)}: animando imagem...")
            print(f"    Movimento: {prompt_mov}")

            ts = time.time() - 1

            try:
                # Clica no botão "Criar novo projeto" ou "New"
                new_btn = page.locator(
                    "button:has-text('New'), button:has-text('Novo'), "
                    "button:has-text('Create'), a:has-text('New Project'), "
                    "[aria-label*='New'], [aria-label*='Criar']"
                ).first
                if new_btn.is_visible(timeout=5_000):
                    new_btn.click()
                    time.sleep(2)

                # Procura e ativa o modo "Frame to Video" / "Fotograma inicial"
                frame_btn = page.locator(
                    "button:has-text('Frame to Video'), "
                    "button:has-text('Fotograma'), "
                    "[aria-label*='Frame to Video'], "
                    "button:has-text('Image to Video')"
                ).first
                if frame_btn.is_visible(timeout=8_000):
                    frame_btn.click()
                    time.sleep(1.5)

                # Upload da imagem
                print(f"    📤 Fazendo upload: {Path(imagem_path).name}")
                
                # Tenta via file input
                with page.expect_file_chooser(timeout=10_000) as fc_info:
                    page.locator(
                        "button:has-text('Upload'), button:has-text('Add'), "
                        "[class*='upload'], .upload-btn, [aria-label*='upload']"
                    ).first.click()
                fc = fc_info.value
                fc.set_files(imagem_path)
                time.sleep(2)

                # Digita o prompt de movimento
                prompt_field = page.locator(
                    "textarea, [placeholder*='Describe'], [placeholder*='descreva'], "
                    "[contenteditable='true']"
                ).first
                if prompt_field.is_visible(timeout=5_000):
                    prompt_field.click()
                    prompt_field.fill(prompt_mov)
                    time.sleep(1)

                # Clica em Gerar / Generate
                gerar_btn = page.locator(
                    "button:has-text('Generate'), button:has-text('Gerar'), "
                    "button:has-text('Create'), button[type='submit'], "
                    "[aria-label*='Generate']"
                ).first
                gerar_btn.wait_for(state="visible", timeout=10_000)
                gerar_btn.click()

                print(f"    ⏳ Aguardando geração do vídeo (até {TIMEOUT_GERACAO//1000}s)...")

                # Aguarda o download aparecer na pasta
                novo_video = aguardar_novo_video(
                    VIBES_DOWNLOAD_DIR,
                    ts,
                    timeout_s=TIMEOUT_GERACAO // 1000,
                )

                if novo_video:
                    shutil.copy2(novo_video, dest)
                    print(f"    ✅ Vídeo salvo: {dest.name} (de {novo_video.name})")
                else:
                    # Tenta clicar no botão de download dentro da interface
                    print("    ⚠️  Download automático não detectado. Tentando via interface...")
                    
                    # Aguarda o vídeo aparecer na timeline/projeto
                    page.wait_for_selector(
                        "video, [class*='video-thumb'], [class*='clip']",
                        timeout=60_000,
                    )
                    time.sleep(2)

                    # Clica no botão de download
                    with page.expect_download(timeout=60_000) as dl_info:
                        page.locator(
                            "button:has-text('Download'), button[aria-label*='Download'], "
                            "[class*='download']"
                        ).first.click()
                    dl = dl_info.value
                    dl.save_as(str(dest))
                    print(f"    ✅ Vídeo baixado via interface: {dest.name}")

            except PlaywrightTimeout as e:
                print(f"    ❌ Timeout na cena {num}: {e}", file=sys.stderr)

            except Exception as e:
                print(f"    ❌ Erro na cena {num}: {e}", file=sys.stderr)

            # Delay entre cenas
            if num < len(cenas):
                print(f"    ⏸️  Aguardando {DELAY_ENTRE_CENAS}s...")
                time.sleep(DELAY_ENTRE_CENAS)
                page.goto("https://vibes.ai/", wait_until="domcontentloaded")
                time.sleep(3)

        context.close()

    # Verifica resultados
    gerados = [TEMP_DIR / f"video_cena_{c['numero']:02d}.mp4" for c in cenas]
    ok  = [v for v in gerados if v.exists()]
    nok = [v for v in gerados if not v.exists()]

    print(f"\n✅ Vídeos gerados: {len(ok)}/{len(cenas)}")
    if nok:
        print(f"⚠️  Faltando: {[v.name for v in nok]}")


if __name__ == "__main__":
    try:
        automacao_vibes()
    except Exception as e:
        print(f"❌ ERRO FATAL: {e}", file=sys.stderr)
        sys.exit(1)
