# Optional custom GPT alternative

This is the original GPT Actions integration. It is **not required** for the My Proton Calendar plugin. Use the plugin setup in [README.md](README.md) for the current default workflow. Choose one ChatGPT integration; both reuse the same NAS adapter.

## Create a private calendar GPT

Open the GPT editor on ChatGPT's web interface (phone browser desktop mode may help). Verify your Plus account exposes custom GPT creation and Actions. Create "My Proton Calendar", keep visibility **Only me**, and paste `gpt-instructions.txt` into its instructions.

Add an Action, importing `https://YOUR_PUBLIC_HOST/openapi.json`. Confirm the schema's `servers` URL matches that hostname; it comes from `PUBLIC_URL`. Alternatively paste the included `openapi.json`, replacing its placeholder server URL first. Choose **API Key → Bearer**, and paste the value stored in `secrets/action_api_key` directly into the GPT editor's authentication setting. Never put it in chat, the OpenAPI schema, a URL, or published source.

The Action key is shared with OpenAI so ChatGPT can call your server. Your Proton password and bridge password stay on your NAS. Keep this GPT private: publishing it with a shared Action key could grant other users access to your calendar adapter.

The write operation has `x-openai-isConsequential: false` so ChatGPT can offer its "Always allow" control for routine personal event creation. Initial approval or product-specific confirmations may still appear. This is not a promise that every action runs without a prompt. It only creates individual events, with no guests, deletion, or editing tools.

Open the saved GPT in the ChatGPT app on your phone. Typed input or keyboard dictation are the initial target; live voice-mode Action support is not verified.


For GPT Action-specific configuration, see [OpenAI’s Actions documentation](https://developers.openai.com/api/docs/actions/introduction).
