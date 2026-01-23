"""UI components and styles for UBA."""
from .styles import (
    APP_NAME_CN,
    APP_NAME_EN,
    APP_FULL_NAME,
    APP_SLOGAN,
    COLORS,
    GLOBAL_CSS,
    get_page_config,
    render_header,
    render_main_header,
    render_metric_card,
    render_alert,
    render_footer,
    get_status_style,
    format_change
)
from .auth import require_auth, render_auth_sidebar, get_current_user_id

__all__ = [
    'APP_NAME_CN',
    'APP_NAME_EN',
    'APP_FULL_NAME',
    'APP_SLOGAN',
    'COLORS',
    'GLOBAL_CSS',
    'get_page_config',
    'render_header',
    'render_main_header',
    'render_metric_card',
    'render_alert',
    'render_footer',
    'get_status_style',
    'format_change',
    'require_auth',
    'render_auth_sidebar',
    'get_current_user_id'
]
