import streamlit as st
from Bio import Entrez
import time
from datetime import datetime, timedelta
from itertools import combinations

def check_author_publications(author_name, email, min_articles=3):
    Entrez.email = email
    today = datetime.now()
    five_years_ago = today - timedelta(days=5 * 365)
    date_range = f"{five_years_ago.strftime('%Y/%m/%d')}[PDat] : {today.strftime('%Y/%m/%d')}[PDat]"
    author_query = f"({author_name}[Author]) AND {date_range}"
    try:
        handle = Entrez.esearch(db="pubmed", term=author_query, retmax=0)
        record = Entrez.read(handle)
        handle.close()
        total_articles = int(record["Count"])
        return total_articles >= min_articles
    except Exception as e:
        st.error(f"Помилка при перевірці автора {author_name}: {e}")
        return False

def check_for_joint_publications(author_name, student_name, email):
    Entrez.email = email
    joint_query = f"({author_name}[Author]) AND ({student_name}[Author])"
    try:
        handle = Entrez.esearch(db="pubmed", term=joint_query, retmax=0)
        record = Entrez.read(handle)
        handle.close()
        total_joint_articles = int(record["Count"])
        return total_joint_articles > 0
    except Exception as e:
        st.error(f"Помилка при перевірці спільних публікацій для автора {author_name} та аспіранта {student_name}: {e}")
        return False

def search_pubmed_by_criteria(email, keywords, required_authors, min_keyword_matches, student_name, batch_size=50):
    Entrez.email = email
    if len(keywords) < min_keyword_matches:
        st.warning("Кількість ключових слів менша за мінімальну кількість збігів.")
        return {}

    keyword_combinations = list(combinations(keywords, min_keyword_matches))
    keyword_query_parts = [f"({' AND '.join(combo)})" for combo in keyword_combinations]
    main_keyword_query = ' OR '.join(keyword_query_parts)

    today = datetime.now()
    five_years_ago = today - timedelta(days=5 * 365)
    date_range = f"{five_years_ago.strftime('%Y/%m/%d')}[PDat] : {today.strftime('%Y/%m/%d')}[PDat]"
    full_query = f"({main_keyword_query}) AND {date_range}"

    st.info(f"Повний пошуковий запит: {full_query}")

    try:
        handle = Entrez.esearch(db="pubmed", term=full_query, retmax=0, usehistory="y")
        record = Entrez.read(handle)
        handle.close()
        total_articles = int(record["Count"])
        st.info(f"Знайдено загалом {total_articles} статей за початковим запитом.")
        if total_articles == 0:
            return {}

        webenv = record["WebEnv"]
        query_key = record["QueryKey"]
        found_authors = {}
        retrieved_count = 0
        progress_bar = st.progress(0)

        while len(found_authors) < required_authors and retrieved_count < total_articles:
            progress_bar.progress(min(1.0, retrieved_count / total_articles))
            st.info(f"Отримання статей... Знайдено кваліфікованих авторів: {len(found_authors)}/{required_authors}. Переглянуто: {retrieved_count}/{total_articles}.")

            handle = Entrez.efetch(db="pubmed", retmode="xml", retstart=retrieved_count, retmax=batch_size, webenv=webenv, query_key=query_key)
            records = Entrez.read(handle)
            handle.close()

            if 'PubmedArticle' not in records or not records['PubmedArticle']:
                st.info("Досягнуто кінця результатів.")
                break

            for pubmed_article in records['PubmedArticle']:
                title = pubmed_article['MedlineCitation']['Article']['ArticleTitle'].lower()
                abstract = ""
                if 'Abstract' in pubmed_article['MedlineCitation']['Article']:
                    abstract_blocks = pubmed_article['MedlineCitation']['Article']['Abstract']['AbstractText']
                    abstract = " ".join([block.lower() for block in abstract_blocks])
                article_text = f"{title} {abstract}"
                keyword_matches_count = sum(1 for keyword in keywords if keyword.lower() in article_text)

                if keyword_matches_count >= min_keyword_matches:
                    if 'AuthorList' in pubmed_article['MedlineCitation']['Article']:
                        for author in pubmed_article['MedlineCitation']['Article']['AuthorList']:
                            if 'AffiliationInfo' in author:
                                for affiliation in author['AffiliationInfo']:
                                    if 'Affiliation' in affiliation:
                                        affiliation_text = affiliation['Affiliation'].lower()
                                        if any(ukr_word in affiliation_text for ukr_word in ["ukraine", "ukrainian", "україна", "україни", "україні"]):
                                            author_name = ""
                                            if 'LastName' in author and 'Initials' in author:
                                                author_name = f"{author['LastName']} {author['Initials']}"
                                            elif 'CollectiveName' in author:
                                                author_name = author['CollectiveName']

                                            if author_name and author_name not in found_authors:
                                                st.info(f"Перевірка автора: {author_name}...")
                                                if check_author_publications(author_name, email, min_articles=3):
                                                    if not check_for_joint_publications(author_name, student_name, email):
                                                        found_authors[author_name] = {
                                                            'affiliation': affiliation['Affiliation'],
                                                            'articles': [{
                                                                'PMID': pubmed_article['MedlineCitation']['PMID'],
                                                                'Title': pubmed_article['MedlineCitation']['Article']['ArticleTitle'],
                                                                'Keyword_matches': keyword_matches_count
                                                            }]
                                                        }
                                                        if len(found_authors) >= required_authors:
                                                            return found_authors
                                                    else:
                                                        st.warning(f"Автор {author_name} має спільні публікації з аспірантом {student_name}.")
                                                else:
                                                    st.warning(f"Автор {author_name} не відповідає критерію мінімум 3 статті.")
            retrieved_count += batch_size
            time.sleep(1)

        progress_bar.empty()
        return found_authors

    except Exception as e:
        st.error(f"Виникла помилка: {e}")
        return {}

# --- Streamlit UI (Інтерфейс користувача)
st.title("Med-Explorer 1.0" )
st.header("Пошук наукових статей на PubMed")
st.markdown("---")


user_email = st.text_input("Будь ласка, введіть вашу електронну пошту (обов'язково): ", help="Цей email потрібен для ідентифікації запитів до PubMed.")

keywords_count = st.number_input("Введіть кількість ключових слів для пошуку:", min_value=1, value=3)
keywords_list = [st.text_input(f"Ключове слово #{i+1}:", key=f"keyword_{i}") for i in range(keywords_count)]
authors_count = st.number_input("Введіть мінімальну кількість унікальних авторів з України, яких потрібно знайти:", min_value=1, value=1)
keyword_matches_count = st.slider(f"Мінімальна кількість збігів ключових слів у статті:", 1, keywords_count, 1)
student_name = st.text_input("Введіть повне ім'я аспіранта для перевірки на спільні публікації (наприклад, Vasylenko M):")

st.markdown("---")

if st.button("Почати пошук"):
    if not user_email:
        st.error("Будь ласка, введіть електронну пошту.")
    elif not all(keywords_list):
        st.error("Будь ласка, введіть усі ключові слова.")
    else:
        st.info("Починаємо пошук...")
        results = search_pubmed_by_criteria(
            email=user_email,
            keywords=keywords_list,
            required_authors=authors_count,
            min_keyword_matches=keyword_matches_count,
            student_name=student_name
        )

        if results:
            st.success(f"Знайдено {len(results)} унікальних авторів з України, що відповідають критеріям!")
            for author_name, author_data in results.items():
                st.header(f"Автор: {author_name}")
                st.markdown(f"**Афіляція:** {author_data['affiliation']}")
                st.subheader("Знайдена стаття:")
                for i, article in enumerate(author_data['articles']):
                    st.markdown(f"**PMID:** {article['PMID']} | **Кількість збігів:** {article['Keyword_matches']}")
                    st.markdown(f"**Заголовок:** _{article['Title']}_")
        else:
            st.warning("Авторів, що відповідають критеріям, не знайдено.")
