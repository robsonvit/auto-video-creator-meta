"""
01_gerar_roteiro.py
───────────────────
Gera o roteiro estruturado do vídeo via OpenRouter API (modelo free).

Recebe os parâmetros via variáveis de ambiente (GitHub Actions):
  TEMA               → Assunto do vídeo
  DURACAO_SEGUNDOS   → Duração desejada (padrão 30)
  ESTILO             → Estilo da narração (padrão "educativo")
  OPENROUTER_API_KEY → Chave da API

Saída: temp/roteiro.json
"""

import os
import json
import math
import sys
from pathlib import Path

import requests

# ── Configurações ─────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL     = "https://openrouter.ai/api/v1/chat/completions"
MODEL              = os.environ.get("MODELO_ROTEIRO", "meta-llama/llama-3.2-3b-instruct:free")

TEMA             = os.environ.get("TEMA", "Curiosidades incríveis sobre o universo")
DURACAO          = int(os.environ.get("DURACAO_SEGUNDOS", "30"))
ESTILO           = os.environ.get("ESTILO", "educativo")
DURACAO_CENA     = 5   # Vibes gera clipes de 5s fixos
NUM_CENAS        = math.ceil(DURACAO / DURACAO_CENA)

TEMP_DIR         = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)
OUTPUT_FILE      = TEMP_DIR / "roteiro.json"

# ── Prompt do sistema ─────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Você é um roteirista especializado em criar vídeos virais curtos para redes sociais.
Sua tarefa é criar roteiros estruturados em JSON.
Seja direto, envolvente e use linguagem natural em português brasileiro.
Retorne APENAS o JSON válido, sem nenhum texto extra antes ou depois."""

USER_PROMPT = f"""Crie um roteiro para um vídeo de {DURACAO} segundos sobre: "{TEMA}"
Estilo de narração: {ESTILO}

O vídeo terá exatamente {NUM_CENAS} cenas de {DURACAO_CENA} segundos cada.

Retorne um JSON com esta estrutura exata:
{{
  "titulo": "Título chamativo do vídeo",
  "tema": "{TEMA}",
  "duracao_total_segundos": {DURACAO},
  "cenas": [
    {{
      "numero": 1,
      "narracao": "Texto completo da narração para esta cena (máximo 40 palavras, ritmo natural para {DURACAO_CENA}s de áudio)",
      "prompt_imagem": "Detailed English visual prompt for AI image generation, cinematic, photorealistic, 16:9, no text, no logos. Describe exactly what should appear in this scene.",
      "prompt_movimento": "Brief English description of subtle camera movement for video animation (e.g.: slow zoom in, gentle pan left, subtle dolly forward)",
      "duracao_segundos": {DURACAO_CENA}
    }}
  ]
}}

Gere exatamente {NUM_CENAS} cenas. As narrações devem fluir naturalmente como um único vídeo coeso."""


def gerar_roteiro() -> dict:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY não definida!")

    print(f"🎬 Gerando roteiro: '{TEMA}' | {DURACAO}s | {NUM_CENAS} cenas")
    print(f"   Modelo: {MODEL}")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com",
        "X-Title": "Auto Video Creator",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": USER_PROMPT},
        ],
        "temperature": 0.8,
        "max_tokens": 2000,
    }

    resp = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=60)

    if resp.status_code != 200:
        raise RuntimeError(f"OpenRouter retornou {resp.status_code}: {resp.text[:400]}")

    content = resp.json()["choices"][0]["message"]["content"].strip()

    # Remove blocos de código markdown se presentes
    if content.startswith("```"):
        lines = content.splitlines()
        content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    roteiro = json.loads(content)

    # Validação básica
    assert "cenas" in roteiro, "JSON sem campo 'cenas'"
    assert len(roteiro["cenas"]) == NUM_CENAS, (
        f"Esperado {NUM_CENAS} cenas, recebido {len(roteiro['cenas'])}"
    )

    OUTPUT_FILE.write_text(json.dumps(roteiro, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ Roteiro salvo em: {OUTPUT_FILE}")
    print(f"   Título: {roteiro.get('titulo', '?')}")
    for c in roteiro["cenas"]:
        print(f"   Cena {c['numero']}: {c['narracao'][:60]}...")

    return roteiro


if __name__ == "__main__":
    try:
        gerar_roteiro()
    except Exception as e:
        print(f"❌ ERRO: {e}", file=sys.stderr)
        sys.exit(1)
