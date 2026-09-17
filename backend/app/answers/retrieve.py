"""Búsqueda semántica sobre el banco de respuestas.

Esto es lo que en M4 (Live Mode) reemplaza al detector de intención +
prefetch del documento original: en vez de clasificar la pregunta en una
categoría fija y luego "preparar contexto", se busca directamente la
respuesta más parecida por embeddings. Es más simple y más rápido.

Uso:
    cd backend
    .venv\\Scripts\\python -m app.answers.retrieve "what technologies have you worked with?"
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from app.answers.store import MODEL_NAME, load_answer, load_index

_model = None  # se carga una sola vez (lazy singleton)


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME, device="cpu")
    return _model


def search(query: str, top_k: int = 3) -> list[dict]:
    """Devuelve hasta `top_k` respuestas del banco más parecidas a `query`,
    ordenadas por similitud coseno descendente, cada una con su `score`."""
    embeddings, metadata = load_index()
    model = _get_model()
    query_embedding = model.encode([query], normalize_embeddings=True, convert_to_numpy=True)[0]

    # Embeddings ya normalizados -> producto punto == similitud coseno.
    scores = embeddings @ query_embedding
    top_indices = np.argsort(-scores)[:top_k]

    results = []
    for idx in top_indices:
        meta = metadata[int(idx)]
        results.append({**meta, "score": float(scores[idx])})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="pregunta a buscar")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--full", action="store_true", help="mostrar la respuesta completa, no solo el id")
    args = parser.parse_args()

    _get_model()  # calentar el modelo antes de medir: en el servidor (M4) esto ya está caliente

    t0 = time.perf_counter()
    results = search(args.query, top_k=args.top_k)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    print(f"\nBúsqueda: {args.query!r}  ({elapsed_ms:.1f} ms, modelo ya cargado)\n")
    for r in results:
        print(f"[{r['score']:.3f}] {r['id']} ({r['category']}) — {r['question_en']}")
        if args.full:
            answer = load_answer(r["id"])
            print(f"    EN: {answer['answer_en']}")
            print(f"    keypoints: {', '.join(answer.get('keypoints', []))}")
        print()


if __name__ == "__main__":
    main()
