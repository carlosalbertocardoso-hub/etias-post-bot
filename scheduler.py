import schedule
import time
import yaml
from scraper import get_new_articles, fetch_article_content, load_posted, save_posted
from agent import generate_post
from publisher import publish_post

with open("config.yaml") as f:
    config = yaml.safe_load(f)


def run_daily_job():
    print("Buscando articulos nuevos en etias.com...")
    new_articles = get_new_articles(config["source_url"])

    if not new_articles:
        print("No hay articulos nuevos hoy.")
        return

    article = new_articles[0]
    print(f"Procesando: {article['title']}")

    source_data = fetch_article_content(article["url"])

    post_data = generate_post(
        source_data["title"],
        source_data["content"],
        source_data["url"]
    )

    post_id = publish_post(
        title=post_data["title"],
        content=post_data["content"],
        categories=post_data["categories"],
        image_url=source_data.get("image_url"),
        status=config["post_status"]
    )

    if post_id:
        posted = load_posted()
        posted.append(article["url"])
        save_posted(posted)


if __name__ == "__main__":
    print(f"Agente iniciado. Publicara 1 borrador/dia a las {config['schedule_time']}")
    run_daily_job()
    schedule.every().day.at(config["schedule_time"]).do(run_daily_job)
    while True:
        schedule.run_pending()
        time.sleep(60)
