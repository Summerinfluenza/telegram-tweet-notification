# AI provider setup

The AI writes the summary, the QQQ/SPY bull/bear
read and the ticker list. Pick one provider; you
can switch any time by changing two lines.

All three work the same way in the code (they
share the "OpenAI chat" format), so the alerts
look the same whichever you choose.

## Compare

**DeepSeek**
- Cheapest paid option, about $0.07/month at 10
  posts/day
- Key: platform.deepseek.com → API keys
- Default model: `deepseek-v4-flash`

**Gemini (Google)**
- Free tier usually covers this bot
- Key: aistudio.google.com → Get API key
- Default model: `gemini-flash-latest`
- Note: on the free tier Google may use requests
  to improve its products. Only the public post
  text and prices are sent.

**OpenAI (ChatGPT)**
- About $0.05–0.10/month at 10 posts/day
- Key: platform.openai.com → API keys (needs
  prepaid credits)
- Default model: `gpt-5-mini`

## Settings

```bash
sudo nano /etc/telegram-tweet-notification.env
```

```
AI_PROVIDER=deepseek
AI_API_KEY=sk-...
AI_MODEL=
```

- `AI_PROVIDER`: `deepseek`, `gemini`, `openai`,
  or `none` (raw posts, no analysis)
- `AI_API_KEY`: the key from that provider
- `AI_MODEL`: leave empty for the default above,
  or name another model from that provider

Then test:

```bash
sudo /opt/telegram-tweet-notification/deploy/check.sh
```

Look for
`✅ AI analysis: deepseek / deepseek-v4-flash → QQQ …`

## Models change

Providers rename and retire models. If the check
says `AI model '…' not found`, look up a current
model on the provider's site and set `AI_MODEL`.
The defaults live in `PROVIDERS` in
`notifier/analysis.py`.

## Another OpenAI-compatible provider

Set `AI_PROVIDER=openai`, put the provider's URL
in `AI_BASE_URL` (e.g. `https://openrouter.ai/api/v1`)
and its model name in `AI_MODEL`.

## Changing what the AI writes

The instructions are in `SYSTEM_PROMPT` in
`notifier/analysis.py`. Change the rules there
(e.g. add a timeframe or style), keep the JSON
shape, and run `pytest`.

## If the AI is down

The alert is still sent: the raw post plus prices,
with `⚠️ AI analysis unavailable`. Details are in
the log.
