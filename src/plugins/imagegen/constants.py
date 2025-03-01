"""Constants for the imagegen plugin."""
from typing import Dict, Any

# Default configuration for imagegen
DEFAULT_CONFIG = {
    "model": "wai_illistrious",
    "negative_prompt": "low quality, bad anatomy, worst quality, low resolution",
    "cfg_scale": 5.0,
    "loras": [],
    "scheduler": "dpm_2m_sde_karras",
    "image_size": "square_hd"
}

# Available models and loras - these will be populated from the database with each call
AVAILABLE_MODELS = {}
AVAILABLE_LORAS = {}

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
    "TCD": "tcd"
}

# Available image sizes with human-readable names
IMAGE_SIZES = {
    "square_hd": "Квадрат HD (1024×1024)",
    "square": "Квадрат (512×512)",
    "portrait_4_3": "Портрет 4:3 (768×1024)",
    "portrait_16_9": "Портрет 16:9 (576×1024)",
    "landscape_4_3": "Пейзаж 4:3 (1024×768)",
    "landscape_16_9": "Пейзаж 16:9 (1024×576)"
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

# Function to load models and loras from database
async def load_models_and_loras():
    """Load models and loras from database."""
    from .repository import ImagegenModelRepository
    
    global AVAILABLE_MODELS, AVAILABLE_LORAS
    
    try:
        # Initialize repository
        repo = ImagegenModelRepository()
        await repo.initialize()
        
        # Load models from database
        models_dict = await repo.get_models_dict()
        AVAILABLE_MODELS.clear()
        
        # Get model names for display
        models = await repo.get_all_models(active_only=True)
        for model in models:
            if model["id"] in models_dict:
                AVAILABLE_MODELS[model["name"]] = model["id"]
        
        # Load loras from database
        loras_dict = await repo.get_loras_dict()
        AVAILABLE_LORAS.clear()
        
        # Get lora names for display
        loras = await repo.get_all_loras(active_only=True)
        for lora in loras:
            if lora["id"] in loras_dict:
                AVAILABLE_LORAS[lora["name"]] = lora["id"]
    except Exception as e:
        # Log error but don't fallback to defaults
        from structlog import get_logger
        log = get_logger(__name__)
        log.error("Error loading models and loras from database", error=str(e))