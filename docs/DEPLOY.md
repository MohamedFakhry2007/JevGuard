# Deploy the demo (Streamlit Community Cloud, free, no key)

The demo runs in replay mode: it shows recorded real Jev answers for the saved examples and needs no API key.
Custom text works only in the clearly labeled simulated mode (a keyword stand-in, not Jev).

1. Sign in at https://share.streamlit.io with the GitHub account that owns the repository.
2. New app, then pick the repository `MohamedFakhry2007/JevGuard`, branch `main`.
3. Main file path: `app/streamlit_app.py`. Under Advanced settings choose Python 3.12.
4. Do not add any secret. Without `TYPESAFE_API_KEY` the app offers only recorded and simulated modes.
5. Deploy. The first build installs `requirements.txt` (`-e .`), which pulls VLM-Guard from GitHub.
6. Put the app URL in `README.md`. The current deployment is https://jevguard-3vezyvexf6dabzamynrpfr.streamlit.app/

The GIF at the top of the README comes from `docs/media/make_demo_gif.py`.
