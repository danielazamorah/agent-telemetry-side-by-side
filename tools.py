# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""The three tools both agents share. Plain Python, no framework imports.

They wait a little so you can see the tool spans in a waterfall, and they never
call the network, so every run is reproducible. They are async so that when the
model asks for two tools at once, both frameworks really run them at the same time.
"""

import asyncio

WEATHER = {"lisbon": {"saturday": "22C, sunny", "sunday": "20C, light clouds"}}
EVENTS = {"lisbon": [{"name": "Fado night at Alfama", "price": 35.0, "currency": "EUR"}]}
RATES = {("EUR", "USD"): 1.09}


async def get_weather(city: str) -> dict:
    """Returns the weekend weather forecast for a city.

    Args:
        city: City name, for example "Lisbon".
    """
    await asyncio.sleep(0.7)
    forecast = WEATHER.get(city.strip().lower())
    return {"city": city, "forecast": forecast} if forecast else {"error": f"No forecast for {city}"}


async def get_events(city: str) -> dict:
    """Returns events in a city this weekend, with ticket prices.

    Args:
        city: City name, for example "Lisbon".
    """
    await asyncio.sleep(0.9)
    events = EVENTS.get(city.strip().lower())
    return {"city": city, "events": events} if events else {"error": f"No events for {city}"}


async def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    """Converts an amount between currencies.

    Args:
        amount: Amount to convert.
        from_currency: ISO code, for example "EUR".
        to_currency: ISO code, for example "USD".
    """
    await asyncio.sleep(0.5)
    rate = RATES.get((from_currency.upper(), to_currency.upper()))
    return {"converted": round(amount * rate, 2), "rate": rate} if rate else {"error": "No rate"}


INSTRUCTION = (
    "You are a trip concierge. Use the tools. When two tools are independent, "
    "call them at the same time. Answer in two sentences."
)

QUESTIONS = {
    # needs two independent tools: the model can ask for both at once
    "parallel": "I'm flying to Lisbon this weekend. What's the weather, and what's on?",
    # the second tool needs the first tool's answer: a staircase
    "serial": "How much is the Fado night in Lisbon in US dollars?",
}
