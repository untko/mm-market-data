# Max Energy fuel-price source

The fuel collector now uses the public API configuration embedded in Max Energy
Myanmar's fuel-price page instead of scraping GlobalPetrolPrices with Chromium.

Max Energy publishes MMK/litre prices for each station and may return multiple
intraday records. The collector mirrors the webpage by excluding station IDs 22
and 24, retaining the latest record per station and grade, ignoring zero prices,
and reporting the median for 95-octane gasoline and diesel. Existing USD fields
are retained by dividing the direct MMK pump prices by the collected market
USD/MMK rate.

The API is queried one day at a time using Yangon dates. Because daily requests
can be slow, the collector uses a 90-second timeout and retries transient request
failures up to five times. Discovering the endpoint and public API key from the
page keeps the collector aligned with the source page without storing a copied
key in the repository.

The change removes Playwright and Chromium from local and CI setup.
