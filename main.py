from openai import OpenAI

client = OpenAI(
  api_key="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"
)

completion = client.chat.completions.create(
  model="gpt-4o-mini",
  store=True,
  messages=[
    {"role": "user", "content": "write a haiku about ai"}
  ]
)

print(completion.choices[0].message);
