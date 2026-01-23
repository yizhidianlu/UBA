"""Authentication UI helpers."""
from __future__ import annotations

import streamlit as st

from ..services.auth_service import AuthService


def require_auth(session) -> AuthService:
    """Ensure the user is authenticated before continuing."""
    auth_service = AuthService(session)
    if st.session_state.get("auth_user"):
        return auth_service

    st.markdown("### 🔐 登录")
    login_tab, register_tab = st.tabs(["登录", "注册"])

    with login_tab:
        login_email = st.text_input("邮箱", key="login_email")
        login_password = st.text_input("密码", type="password", key="login_password")
        if st.button("登录", type="primary", use_container_width=True):
            if not login_email or not login_password:
                st.warning("请输入邮箱和密码")
            else:
                result = auth_service.authenticate(login_email, login_password)
                if result:
                    st.session_state.auth_user = {
                        "id": result.user.id,
                        "email": result.user.email
                    }
                    st.success("✅ 登录成功")
                    st.rerun()
                else:
                    st.error("邮箱或密码错误")

    with register_tab:
        register_email = st.text_input("邮箱", key="register_email")
        register_password = st.text_input("密码", type="password", key="register_password")
        register_confirm = st.text_input("确认密码", type="password", key="register_confirm")
        if st.button("注册", use_container_width=True):
            if not register_email or not register_password:
                st.warning("请输入邮箱和密码")
            elif register_password != register_confirm:
                st.warning("两次输入的密码不一致")
            elif "@" not in register_email:
                st.warning("请输入有效邮箱")
            else:
                try:
                    result = auth_service.register_user(register_email, register_password)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.session_state.auth_user = {
                        "id": result.user.id,
                        "email": result.user.email
                    }
                    st.success("✅ 注册成功")
                    st.rerun()

    st.stop()


def render_auth_sidebar() -> None:
    """Render auth status and logout in sidebar."""
    user = st.session_state.get("auth_user")
    if not user:
        return
    st.sidebar.markdown(f"**已登录:** {user['email']}")
    if st.sidebar.button("退出登录", use_container_width=True):
        st.session_state.pop("auth_user", None)
        st.rerun()


def get_current_user_id() -> int:
    user = st.session_state.get("auth_user")
    if not user:
        raise RuntimeError("User is not authenticated")
    return user["id"]
