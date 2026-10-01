"""
05_montar_video.py
──────────────────
Monta o vídeo final a partir dos clips gerados pelo Vibes.ai.

Pipeline:
  1. Coleta todos os clips temp/video_cena_NN.mp4
  2. Normaliza resolução e framerate com ffprobe + ffmpeg
  3. Concatena com transição xfade (fade) entre cada clip
  4. Mixtura narração (cada cena sincronizada) + música de fundo
  5. Exporta output/video_YYYYMMDD_HHMMSS.mp4 usando GPU (NVENC)
  6. Limpa toda a pasta temp/ automaticamente

Requisitos: FFmpeg com suporte NVENC (build do gyan.dev para Windows)
GPU:        NVIDIA com driver recente (Turing/Ampere/Ada recomendado)
"""

import os
import json
import sys
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

# ── Configurações ─────────────────────────────────────────────────────────────
TEMP_DIR       = Path("temp")
OUTPUT_DIR     = Path("output")
ROTEIRO_FILE   = TEMP_DIR / "roteiro.json"
MUSICA_FUNDO   = Path(os.environ.get("MUSICA_FUNDO", "music/background.mp3"))

RESOLUCAO      = os.environ.get("RESOLUCAO", "1280x720")
FPS            = int(os.environ.get("FPS", "30"))
DUR_TRANSICAO  = float(os.environ.get("DUR_TRANSICAO", "0.5"))
VOL_MUSICA     = float(os.environ.get("VOL_MUSICA", "0.15"))

# Detectar suporte GPU
USE_GPU = os.environ.get("USE_GPU", "auto").lower()   # "auto", "true", "false"

OUTPUT_DIR.mkdir(exist_ok=True)


# ── Utilitários FFmpeg ────────────────────────────────────────────────────────
def ffprobe_info(path: str) -> dict:
    """Retorna informações do vídeo via ffprobe."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate,duration",
         "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(r.stdout)
    s = data["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return {
        "width":    int(s.get("width", 1280)),
        "height":   int(s.get("height", 720)),
        "fps":      round(int(num) / int(den), 2),
        "duration": float(s.get("duration", 5.0)),
    }


def verificar_nvenc() -> bool:
    """Verifica se o FFmpeg tem suporte ao encoder NVENC."""
    r = subprocess.run(
        ["ffmpeg", "-encoders"], capture_output=True, text=True
    )
    return "h264_nvenc" in r.stdout


def normalizar_clip(input_path: str, output_path: str, use_gpu: bool):
    """
    Normaliza um clip para a resolução e FPS alvo.
    Usa GPU para encode se disponível.
    """
    w, h = RESOLUCAO.split("x")
    encoder = "h264_nvenc" if use_gpu else "libx264"
    preset  = "p4" if use_gpu else "fast"

    cmd = ["ffmpeg", "-y"]
    if use_gpu:
        cmd += ["-hwaccel", "cuda"]
    cmd += [
        "-i", input_path,
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={FPS}",
        "-c:v", encoder,
        "-preset", preset,
        "-crf" if not use_gpu else "-cq", "23",
        "-pix_fmt", "yuv420p",
        "-an",   # Remove áudio (vai ser adicionado depois)
        output_path
    ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg normalizar falhou:\n{r.stderr[-500:]}")


def montar_video_final(clips_norm: list[str], audio_cenas: list[str], 
                        audio_completo: str, output_path: str, use_gpu: bool):
    """
    Monta o vídeo final com:
    - Transições xfade entre clips
    - Narração sincronizada por cena
    - Música de fundo mixada
    """
    n = len(clips_norm)
    encoder = "h264_nvenc" if use_gpu else "libx264"
    preset  = "p4" if use_gpu else "fast"

    # ── Passo 1: Concatenar vídeos com xfade ─────────────────────────────────
    print("  [FFmpeg] Montando vídeo com transições xfade...")

    if n == 1:
        # Apenas 1 clip — não precisa de transição
        video_sem_audio = str(TEMP_DIR / "_video_raw.mp4")
        shutil.copy(clips_norm[0], video_sem_audio)
    else:
        # Constrói filtergraph xfade dinâmico
        # Cada clip tem 5s; offset é acumulativo subtraindo a duração da transição
        dur_clip   = 5.0
        inputs     = []
        for c in clips_norm:
            inputs += ["-i", c]

        # Constrói o filtergraph
        fgraph_parts = []
        last_label   = "[0:v]"
        for i in range(1, n):
            offset = round((dur_clip * i) - (DUR_TRANSICAO * i), 3)
            label_out = f"[v{i}]" if i < n - 1 else "[vout]"
            fgraph_parts.append(
                f"{last_label}[{i}:v]xfade=transition=fade:duration={DUR_TRANSICAO}:"
                f"offset={offset}{label_out}"
            )
            last_label = label_out if i < n - 1 else "[vout]"

        filtergraph = ";".join(fgraph_parts)
        if n == 2:
            # Para 2 clips o label final já é [vout]
            filtergraph = fgraph_parts[0].replace(f"[v1]", "[vout]")

        video_sem_audio = str(TEMP_DIR / "_video_raw.mp4")
        cmd = ["ffmpeg", "-y"]
        if use_gpu:
            cmd += ["-hwaccel", "cuda"]
        cmd += inputs
        cmd += [
            "-filter_complex", filtergraph,
            "-map", "[vout]",
            "-c:v", encoder,
            "-preset", preset,
            "-pix_fmt", "yuv420p",
            video_sem_audio,
        ]

        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg xfade falhou:\n{r.stderr[-800:]}")

    # ── Passo 2: Mixar narrações + música de fundo ────────────────────────────
    print("  [FFmpeg] Mixando áudio (narração + música de fundo)...")

    tem_musica = MUSICA_FUNDO.exists()
    cmd = ["ffmpeg", "-y"]
    if use_gpu:
        cmd += ["-hwaccel", "cuda"]

    cmd += ["-i", video_sem_audio]
    cmd += ["-i", audio_completo]
    if tem_musica:
        cmd += ["-stream_loop", "-1", "-i", str(MUSICA_FUNDO)]

    if tem_musica:
        # Mixar narração (volume total) + música de fundo (volume reduzido)
        audio_filter = (
            f"[1:a]volume=1.0[narr];"
            f"[2:a]volume={VOL_MUSICA}[bgm];"
            f"[narr][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
        cmd += [
            "-filter_complex", audio_filter,
            "-map", "0:v",
            "-map", "[aout]",
        ]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]

    cmd += [
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path,
    ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg mixar áudio falhou:\n{r.stderr[-800:]}")

    print(f"  [FFmpeg] ✅ Vídeo final: {output_path}")


def limpar_temp():
    """Remove toda a pasta temp/ após a montagem."""
    print("\n🧹 Limpando pasta temp/...")
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    TEMP_DIR.mkdir(exist_ok=True)  # Recria vazia para próximas execuções
    (TEMP_DIR / ".gitkeep").touch()
    print("   ✅ Pasta temp/ limpa!")


def montar():
    roteiro = json.loads(ROTEIRO_FILE.read_text(encoding="utf-8"))
    cenas   = roteiro["cenas"]
    titulo  = roteiro.get("titulo", "video")

    # Detecta uso de GPU
    if USE_GPU == "auto":
        use_gpu = verificar_nvenc()
        print(f"🔍 GPU NVENC: {'✅ Disponível' if use_gpu else '❌ Não disponível — usando CPU'}")
    else:
        use_gpu = USE_GPU == "true"

    # Coleta clips gerados
    clips = []
    for cena in cenas:
        v = TEMP_DIR / f"video_cena_{cena['numero']:02d}.mp4"
        if v.exists():
            clips.append(str(v))
        else:
            print(f"  ⚠️  Clip faltando: {v.name} — pulando")

    if not clips:
        raise RuntimeError("Nenhum clip de vídeo encontrado em temp/!")

    audio_completo = str(TEMP_DIR / "audio_completo.mp3")
    audio_cenas    = [str(TEMP_DIR / f"audio_cena_{c['numero']:02d}.mp3") for c in cenas]

    if not Path(audio_completo).exists():
        raise RuntimeError(f"Áudio não encontrado: {audio_completo}")

    print(f"\n🎬 Montando vídeo final...")
    print(f"   Clips: {len(clips)} | Resolução: {RESOLUCAO} | FPS: {FPS}")
    print(f"   Encoder: {'h264_nvenc (GPU)' if use_gpu else 'libx264 (CPU)'}")
    print(f"   Transições: {DUR_TRANSICAO}s fade entre cenas")
    print(f"   Música de fundo: {'✅ ' + str(MUSICA_FUNDO) if MUSICA_FUNDO.exists() else '❌ Não encontrada'}")

    # Normaliza todos os clips
    clips_norm = []
    print(f"\n  Normalizando {len(clips)} clips...")
    for i, clip in enumerate(clips):
        norm = str(TEMP_DIR / f"_norm_{i:02d}.mp4")
        print(f"    [{i+1}/{len(clips)}] {Path(clip).name}")
        normalizar_clip(clip, norm, use_gpu)
        clips_norm.append(norm)

    # Nome do arquivo de saída
    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Sanitiza título para nome de arquivo
    titulo_safe = "".join(c for c in titulo if c.isalnum() or c in " _-")[:40].strip()
    output_name = f"{ts}_{titulo_safe}.mp4" if titulo_safe else f"video_{ts}.mp4"
    output_path = str(OUTPUT_DIR / output_name)

    # Monta vídeo final
    montar_video_final(clips_norm, audio_cenas, audio_completo, output_path, use_gpu)

    # Verifica arquivo final
    if not Path(output_path).exists():
        raise RuntimeError(f"Arquivo final não gerado: {output_path}")

    size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    print(f"\n✅ VÍDEO FINAL: {output_path}")
    print(f"   Tamanho: {size_mb:.1f} MB")

    # Limpa pasta temp
    limpar_temp()

    return output_path


if __name__ == "__main__":
    try:
        montar()
    except Exception as e:
        print(f"❌ ERRO FATAL: {e}", file=sys.stderr)
        sys.exit(1)
