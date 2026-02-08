import streamlit as st

from avaai.chat_page import chat_page


def main() -> None:
    st.set_page_config(
        page_title="Chat",
        page_icon="\U0001F338",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    pages = {
        "Chat": [
            st.Page(chat_page, title="Chat", icon="\U0001F4AC"),
        ],
        "Admin": [
            st.Page("pages/13_Admin.py", title="Overview", icon="\U0001F6E1\ufe0f"),
            st.Page("pages/15_Settings.py", title="Settings", icon="\u2699\ufe0f"),
            st.Page("pages/14_Plugins.py", title="Plugins", icon="\U0001F9E9"),
            st.Page("pages/16_Debug.py", title="Debug", icon="\U0001F9EA"),
        ],
    }

    navigation = st.navigation(pages, expanded=True)
    navigation.run()


if __name__ == "__main__":
    main()

