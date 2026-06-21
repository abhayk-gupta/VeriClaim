from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
import io

from app.auth_deps import get_current_agent
from app.models.agent import Agent
from app.services.media_storage import get_image

router = APIRouter(prefix="/media", tags=["media"])

@router.get("/{r2_key:path}")
async def proxy_media(
    r2_key: str,
    current_agent: Agent = Depends(get_current_agent)
):
    try:
        image_bytes = await get_image(r2_key)
        
        # Simple content type inference (extend if needed)
        content_type = "image/jpeg"
        if r2_key.lower().endswith(".png"):
            content_type = "image/png"
        elif r2_key.lower().endswith(".webp"):
            content_type = "image/webp"
            
        return StreamingResponse(io.BytesIO(image_bytes), media_type=content_type)
    except KeyError:
        raise HTTPException(status_code=404, detail="Media not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving media: {str(e)}")
