"""
03_automacao_metaai.py
──────────────────────
Automatiza a geração e download de imagens no Meta.ai usando
a extensão "Meta Automation" já instalada no Chrome.

Estratégia:
  1. Abre Chrome com perfil persistente real (onde a extensão já está instalada)
  2. Navega para meta.ai
  3. Para cada cena do roteiro:
     a. Digita o prompt_imagem no campo de texto do meta.ai
     b. Submete a geração
     c. Aguarda o download automático da extensão
     d. Move o arquivo baixado para temp/imagem_cena_NN.png

Entrada:  temp/roteiro.json
Saída:    temp/imagem_cena_01.png, imagem_cena_02.png, ...
"""

import os
import json
import sys
import time
import shutil
import glob
from pathlib import Path
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ── Configurações ─────────────────────────────────────────────────────────────
CHROME_USER_DATA = os.environ.get(
    "CHROME_USER_DATA_DIR",
    r"C:\Users\robso\AppData\Local\Google\Chrome\User Data"
)
CHROME_PROFILE   = os.environ.get("CHROME_PROFILE", "Default")

META_DOWNLOAD_DIR = Path(os.environ.get(
    "META_DOWNLOAD_DIR",
    r"C:\Users\robso\Downloads\meta-folder-1"
))

TEMP_DIR     = Path("temp")
ROTEIRO_FILE = TEMP_DIR / "roteiro.json"

# Timeouts
TIMEOUT_GERACAO  = 120_000   # 2 min p/ a imagem ser gerada
TIMEOUT_DOWNLOAD =  90_000   # 1.5 min p/ o download aparecer
DELAY_ENTRE_CENAS = 5        # segundos entre cenas (evita rate limit)


def aguardar_novo_arquivo(pasta: Path, extensoes: list[str], ts_anterior: float, timeout_s: int = 90) -> Path | None:
    """Aguarda um novo arquivo aparecer na pasta após timestamp 'ts_anterior'."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        for ext in extensoes:
            for f in pasta.glob(f"*{ext}"):
                if f.stat().st_mtime > ts_anterior:
                    # Aguarda o arquivo terminar de ser escrito
                    time.sleep(1.5)
                    return f
        time.sleep(1)
    return None


def automacao_metaai():
    roteiro = json.loads(ROTEIRO_FILE.read_text(encoding="utf-8"))
    cenas   = roteiro["cenas"]

    META_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    print(f"🖼️  Gerando {len(cenas)} imagens no Meta.ai...")
    print(f"   Chrome profile: {CHROME_USER_DATA}\\{CHROME_PROFILE}")
    print(f"   Download dir:   {META_DOWNLOAD_DIR}")

    with sync_playwright() as p:
        # Abre Chrome com perfil real (onde as extensões estão instaladas)
        context = p.chromium.launch_persistent_context(
            user_data_dir=CHROME_USER_DATA,
            channel="chrome",
            headless=False,          # Precisa ser headful para extensões funcionarem
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                f"--profile-directory={CHROME_PROFILE}",
            ],
            accept_downloads=True,
        )

        page = context.new_page()
        page.goto("https://www.meta.ai/", wait_until="domcontentloaded")
        print("   Meta.ai carregado. Aguardando 3s para estabilizar...")
        time.sleep(3)

        for cena in cenas:
            num    = cena["numero"]
            prompt = cena["prompt_imagem"]
            dest   = TEMP_DIR / f"imagem_cena_{num:02d}.png"

            print(f"\n  → Cena {num}/{len(cenas)}: gerando imagem...")
            print(f"    Prompt: {prompt[:80]}...")

            # Timestamp antes de começar para detectar arquivo novo
            ts = time.time() - 1

            try:
                # Localiza o textarea do Meta.ai e injeta o prompt
                textarea = page.locator("textarea, [contenteditable='true'], [role='textbox']").first
                textarea.wait_for(timeout=10_000)
                textarea.click()
                textarea.fill("")
                textarea.type(prompt, delay=30)

                # Aguarda o botão de envio e clica
                send_btn = page.locator(
                    "button[aria-label*='Send'], button[aria-label*='Enviar'], "
                    "button[type='submit'], [data-testid='send-button']"
                ).first
                send_btn.wait_for(state="visible", timeout=10_000)
                send_btn.click()

                print(f"    ⏳ Aguardando geração da imagem (até {TIMEOUT_GERACAO//1000}s)...")

                # Aguarda o botão de download aparecer (a extensão o monitora)
                # e ao mesmo tempo verifica se um arquivo novo apareceu na pasta
                novo_arquivo = aguardar_novo_arquivo(
                    META_DOWNLOAD_DIR,
                    [".png", ".jpg", ".jpeg", ".webp"],
                    ts,
                    timeout_s=TIMEOUT_DOWNLOAD // 1000,
                )

                if novo_arquivo:
                    shutil.copy2(novo_arquivo, dest)
                    print(f"    ✅ Imagem salva: {dest.name} (de {novo_arquivo.name})")
                else:
                    # Fallback: tenta fazer screenshot da imagem gerada
                    print("    ⚠️  Download automático não detectado. Tentando screenshot...")
                    img_element = page.locator("img[src*='scontent'], img[src*='fbcdn']").last
                    img_element.wait_for(timeout=30_000)
                    img_element.screenshot(path=str(dest))
                    print(f"    ✅ Screenshot salvo: {dest.name}")

            except PlaywrightTimeout as e:
                print(f"    ❌ Timeout na cena {num}: {e}", file=sys.stderr)
                # Cria imagem placeholder para não travar o pipeline
                _criar_placeholder(dest, f"Cena {num}")

            # Aguarda entre cenas
            if num < len(cenas):
                print(f"    ⏸️  Aguardando {DELAY_ENTRE_CENAS}s antes da próxima cena...")
                time.sleep(DELAY_ENTRE_CENAS)

            # Recarrega a página para próxima geração
            if num < len(cenas):
                page.goto("https://www.meta.ai/", wait_until="domcontentloaded")
                time.sleep(2)

        context.close()

    # Verifica se todas as imagens foram geradas
    faltando = []
    for cena in cenas:
        img = TEMP_DIR / f"imagem_cena_{cena['numero']:02d}.png"
        if not img.exists():
            faltando.append(img.name)

    if faltando:
        print(f"\n⚠️  Imagens faltando: {faltando}")
    else:
        print(f"\n✅ Todas as {len(cenas)} imagens geradas com sucesso!")


def _criar_placeholder(dest: Path, label: str):
    """Cria uma imagem placeholder cinza com texto caso a geração falhe."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (1280, 720), color=(30, 30, 30))
        draw = ImageDraw.Draw(img)
        draw.text((640, 360), f"[{label}]", fill=(200, 200, 200), anchor="mm")
        img.save(str(dest))
    except ImportError:
        # Se Pillow não estiver instalado, cria arquivo vazio
        dest.write_bytes(b"")
    print(f"    ℹ️  Placeholder criado: {dest.name}")


if __name__ == "__main__":
    try:
        automacao_metaai()
    except Exception as e:
        print(f"❌ ERRO FATAL: {e}", file=sys.stderr)
        sys.exit(1)
