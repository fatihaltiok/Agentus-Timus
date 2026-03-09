import deal

from utils.hf_model_pinning import resolve_pinned_revision


@deal.pre(lambda model_name: model_name in {
    "facebook/sam-vit-base",
    "hustvl/yolos-tiny",
    "microsoft/Florence-2-large-ft",
    "microsoft/trocr-base-printed",
    "openai/clip-vit-base-patch32",
    "Qwen/Qwen2-VL-2B-Instruct",
    "Qwen/Qwen2-VL-7B-Instruct",
    "Qwen/Qwen2.5-VL-3B-Instruct",
})
@deal.post(lambda r: isinstance(r, str) and len(r) == 40)
def pinned_revision_contract(model_name: str) -> str:
    return resolve_pinned_revision(model_name, "UNUSED_ENV_OVERRIDE")
