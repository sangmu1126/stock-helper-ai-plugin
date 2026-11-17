# LLM Smoke Test

## Purpose

This document records the real GPT API smoke test for the LLM parser path. Mock tests cover the parser contract, but this check verifies that the OpenAI SDK, Responses API structured outputs, `.env` key loading, schema validation, and post-normalization path work together.

## Command

```powershell
python src\skills\safe-trade-rule-builder\scripts\rule_builder.py `
  --intent "카카오가 전일 종가보다 3% 떨어지면 10만원만 매수 후보로 알려줘" `
  --parser llm `
  --provider demo-fixture `
  --format json
```

## Result

- `parser.source`: `llm`
- `parser.structured_output_used`: `true`
- `parser.fallback_used`: `false`
- `asset.symbol`: `035720.KS`
- `trigger.type`: `price_drop_percent`
- `trigger.reference`: `previous_close`
- `trigger.percent`: `3.0`
- `action`: `prepare_buy_order`
- `execution_mode`: `manual_confirm`
- `order.mode`: `amount`
- `order.value`: `100000`

## Issues Found and Fixed

- The first structured-output call failed because the Pydantic schema did not fully satisfy OpenAI's strict JSON schema requirements.
- `ParserMeta.normalized_from` used an arbitrary dictionary shape, which conflicted with strict structured output. It was replaced with an explicit `NormalizedFrom` model.
- The model initially produced `035720.KQ` for Kakao. The normalizer now corrects known Korean equity market suffix mistakes such as `035720.KQ -> 035720.KS`.
- The model initially interpreted "매수 후보로 알려줘" as `notify_only`. The LLM post-normalizer now treats "매수 후보" and "매도 후보" as manual-confirmation order candidates, not live orders.

## Security

- The API key was loaded from `.env`.
- `.env` is not included in `submission.zip`.
- The final secret scan did not find OpenAI keys, AWS keys, private keys, or common token patterns in `README.md`, `src`, `logs`, `.env.example`, or `tests`.
