# Hermes dashboard plugin

Drop-in tab for `hermes dashboard`. It embeds the Quinovo query + graph UI.

```bash
mkdir -p ~/.hermes/plugins/quinovo
cp -R integrations/hermes-dashboard/. ~/.hermes/plugins/quinovo/
hermes plugins enable quinovo --no-allow-tool-override
quinovo serve   # kernel HTTP, default http://127.0.0.1:8791
hermes dashboard
```

Open the **Quinovo** tab. Query the pack in the search bar. **Extend graph** goes fullscreen.

Override the kernel URL with `QUINOVO_URL` if `serve` is not on 8791.
