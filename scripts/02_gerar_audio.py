"""
02_gerar_audio.py
─────────────────
Gera áudio de narração para cada cena usando Fish Audio API (s2.1-pro-free).

⚠️  GOTCHA CRÍTICO (descoberto no projeto PORRADA):
    O parâmetro "model" DEVE ir no HEADER da requisição HTTP,
    não no body/payload. Passá-lo no payload gera erro 402.

Entrada:  temp/roteiro.json
Saída:    temp/audio_cena_01.mp3, audio_cena_02.mp3, ...
          temp/audio_completo.mp3  (todas as narrações concatenadas)
"""

import os
import json
import sys
import subprocess
from pathlib import Path

import requests

# ── Configurações Fish Audio ──────────────────────────────────────────────────
FISH_API_KEY  = os.environ.get("FISH_API_KEY", "")
FISH_VOICE_ID = os.environ.get("FISH_VOICE_ID", "86f23b6596304f22955de78fe89638fc")
FISH_MODEL    = "s2.1-pro-free"
FISH_API_URL  = "https://api.fish.audio/v1/tts"

TEMP_DIR      = Path("temp")
ROTEIRO_FILE  = TEMP_DIR / "roteiro.json"


def gerar_audio_cena(texto: str, output_mp3: str) -> float:
    """
    Gera áudio MP3 para o texto dado via Fish Audio API.
    Retorna a duração em segundos.
    
    IMPORTANTE: 'model' vai no header, não no payload!
    """
    if not FISH_API_KEY:
        raise RuntimeError("FISH_API_KEY não definida!")

    # ⚠️ model no HEADER — comportamento obrigatório para o tier gratuito
    headers = {
        "Authorization": f"Bearer {FISH_API_KEY}",
        "Content-Type": "application/json",
        "model": FISH_MODEL,          # ← CRÍTICO: header, não body
    }
    payload = {
        "text": texto,
        "reference_id": FISH_VOICE_ID,
        "format": "mp3",
        "mp3_bitrate": 192,
        "normalize": True,
        "latency": "normal",
    }

    print(f"  [Fish Audio] Gerando áudio ({len(texto)} chars)...")
    resp = requests.post(FISH_API_URL, json=payload, headers=headers, timeout=120)

    if resp.status_code != 200:
        raise RuntimeError(
            f"Fish Audio retornou {resp.status_code}: {resp.text[:300]}"
        )

    Path(output_mp3).write_bytes(resp.content)

    # Obtém duração via ffprobe
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", output_mp3],
        capture_output=True, text=True,
    )
    duracao = float(dur.stdout.strip()) if dur.stdout.strip() else 0.0
    print(f"  [Fish Audio] ✅ {Path(output_mp3).name} ({duracao:.1f}s)")
    return duracao


def concatenar_audios(lista_mp3: list[str], output_mp3: str):
    """Concatena múltiplos MP3 num único arquivo via FFmpeg."""
    # Cria lista de arquivos para o ffmpeg
    lista_txt = TEMP_DIR / "_concat_audio.txt"
    with open(lista_txt, "w") as f:
        for mp3 in lista_mp3:
            f.write(f"file '{Path(mp3).resolve()}'\n")

    result = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
         "-i", str(lista_txt), "-c", "copy", output_mp3],
        capture_output=True, text=True,
    )
    lista_txt.unlink(missing_ok=True)

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg concat falhou:\n{result.stderr}")

    print(f"  [Concat] ✅ {output_mp3}")


def gerar_todos_audios():
    roteiro = json.loads(ROTEIRO_FILE.read_text(encoding="utf-8"))
    cenas   = roteiro["cenas"]

    print(f"🔊 Gerando áudio para {len(cenas)} cenas via Fish Audio...")

    arquivos_mp3 = []
    duracoes     = []

    for cena in cenas:
        num  = cena["numero"]
        txt  = cena["narracao"]
        mp3  = str(TEMP_DIR / f"audio_cena_{num:02d}.mp3")

        duracao = gerar_audio_cena(txt, mp3)
        arquivos_mp3.append(mp3)
        duracoes.append(duracao)

    # Salva metadados de duração no roteiro
    for i, cena in enumerate(cenas):
        cena["duracao_audio_real"] = duracoes[i]

    ROTEIRO_FILE.write_text(
        json.dumps(roteiro, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Concatena tudo
    audio_completo = str(TEMP_DIR / "audio_completo.mp3")
    print("\n  Concatenando narrações...")
    concatenar_audios(arquivos_mp3, audio_completo)

    total = sum(duracoes)
    print(f"\n✅ Áudio gerado! Total: {total:.1f}s | Arquivos: {len(arquivos_mp3)} cenas")
    return arquivos_mp3, audio_completo


if __name__ == "__main__":
    try:
        gerar_todos_audios()
    except Exception as e:
        print(f"❌ ERRO: {e}", file=sys.stderr)
        sys.exit(1)
