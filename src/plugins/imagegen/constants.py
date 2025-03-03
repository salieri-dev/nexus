"""Constants for the imagegen plugin."""

# Default configuration for imagegen
DEFAULT_CONFIG = {"model": "checkpoint_827184", "negative_prompt": "bad anatomy, signature, watermark, username, error, missing limbs, error, bad quality,worst quality,worst detail,sketch,censor, cropped, crop", "loras": [], "image_size": "square"}

# Available schedulers - key: display name, value: API value
AVAILABLE_SCHEDULERS = {
    "DPM++ 2M": "dpm_2m",
    "DPM++ 2M Karras": "dpm_2m_karras",
    "DPM++ 2M SDE": "dpm_2m_sde",
    "DPM++ 2M SDE Karras": "dpm_2m_sde_karras",
    "Euler": "euler",
    "Euler A": "euler_a",
    "Euler (trailing timesteps)": "euler_trailing",
    "LCM": "lcm",
    "LCM (trailing timesteps)": "lcm_trailing",
    "DDIM": "ddim",
    "TCD": "tcd",
}

# Available image sizes with human-readable names
IMAGE_SIZES = {
    "square": "Квадрат (512×512)", 
    "portrait_4_3": "Портрет (512×768)", 
    "landscape_4_3": "Пейзаж (768x512)", 
}

# Callback data prefixes
CALLBACK_PREFIX = "imagegen_"
MODEL_CALLBACK = f"{CALLBACK_PREFIX}model_"
NEGATIVE_PROMPT_CALLBACK = f"{CALLBACK_PREFIX}negative_prompt"
CFG_SCALE_CALLBACK = f"{CALLBACK_PREFIX}cfg_scale"
LORAS_CALLBACK = f"{CALLBACK_PREFIX}loras_"
SCHEDULER_CALLBACK = f"{CALLBACK_PREFIX}scheduler_"
IMAGE_SIZE_CALLBACK = f"{CALLBACK_PREFIX}image_size_"
BACK_CALLBACK = f"{CALLBACK_PREFIX}back"

IMAGEGEN_DISABLED = False
