E-Commerce Price Scraper for European Markets

I built this automated web scraper to collect product prices from e-commerce sites across nine European countries. The goal was to create a reliable tool that could handle dynamic JavaScript content and various anti-scraping measures.

Technologies & Features
Core Logic: Python

Browser Automation: Selenium WebDriver (with Firefox/GeckoDriver)

Data Processing & Export: Pandas

Concurrency: Python's threading and queue modules

Key Features:

Scalable to hundreds of URLs across multiple countries.

A persistent browser pool architecture for high stability and performance.

Handles complex popups and cookie banners in multiple languages.

Automates data export to a multi-sheet Excel report, categorized by country.

Key Challenges & My Solutions

Initial Instability

The first version of the scraper was unstable, with frequent browser driver crashes. I solved this by migrating the automation from Chrome to Firefox and implementing a robust cleanup process that fully terminates old processes and clears temporary profiles before each run.

Poor Performance

Once stable, the scraper was too slow for practical use, with a projected runtime of over 8 hours. I re-architected the core logic from launching a new browser for every URL to using a persistent browser pool. This producer-consumer model reduced the total runtime by over 80% and made the tool viable for the client.

Dynamic Content & Anti-Scraping

Many sites blocked content with dynamic cookie banners in various languages. I built a flexible handler that uses a comprehensive list of keywords and selectors to reliably dismiss these popups, which resulted in a final success rate of over 95%.

Final Excel output showing successful data export, separated by country:
![Final Scraper Output](https://github.com/bellecoding/Automated-Price-Scraper/blob/main/output%20image.jpg)



How to Run

Ensure all requirements are installed: pip install -r requirements.txt

Place geckodriver.exe in the project directory.

Run the script: python price_scraper.py

To run in test mode (first 20 URLs): python price_scraper.py --test


Architecture

![Scraper Architecture Diagram](https://github.com/bellecoding/Automated-Price-Scraper/blob/main/ScraperDiagram.drawio.png)

A simple diagram showing the scraper's design. A central queue feeds URLs to multiple browser workers that run in parallel to process the data and save it to the final Excel file.


