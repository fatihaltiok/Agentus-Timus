import os


_PINNED_MODEL_REVISIONS = {
    "facebook/sam-vit-base": "70c1a07f894ebb5b307fd9eaaee97b9dfc16068f",
    "hustvl/yolos-tiny": "95a90f3c189fbfca3bcfc6d7315b9e84d95dc2de",
    "microsoft/Florence-2-large-ft": "4a12a2b54b7016a48a22037fbd62da90cd566f2a",
    "microsoft/trocr-base-printed": "93450be3f1ed40a930690d951ef3932687cc1892",
    "openai/clip-vit-base-patch32": "3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268",
    "Qwen/Qwen2-VL-2B-Instruct": "895c3a49bc3fa70a340399125c650a463535e71c",
    "Qwen/Qwen2-VL-7B-Instruct": "eed13092ef92e448dd6875b2a00151bd3f7db0ac",
    "Qwen/Qwen2.5-VL-3B-Instruct": "66285546d2b821cf421d4f5eb2576359d3770cd3",
}


def resolve_pinned_revision(model_name: str, env_var: str) -> str:
    override = os.getenv(env_var, "").strip()
    if override:
        return override

    revision = _PINNED_MODEL_REVISIONS.get(model_name)
    if revision:
        return revision

    raise RuntimeError(
        f"Kein gepinnter HuggingFace-Revisionseintrag fuer '{model_name}'. "
        f"Setze {env_var}, um einen expliziten Commit-Hash zu konfigurieren."
    )
