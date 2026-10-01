from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

DATA_PATH = Path(__file__).parent / "data" / "movie_ratings.csv"


@st.cache_data
def load_ratings() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    return df


def explode_genres(df: pd.DataFrame) -> pd.DataFrame:
    """Split pipe-separated genres so each row has one genre."""
    out = df.dropna(subset=["genres"]).copy()
    out["genre"] = out["genres"].astype(str).str.split("|")
    out = out.explode("genre")
    out["genre"] = out["genre"].str.strip()
    return out[out["genre"].ne("") & out["genre"].str.lower().ne("nan")]


def top_movies(movie_stats: pd.DataFrame, min_ratings: int, n: int = 5) -> pd.DataFrame:
    eligible = movie_stats[movie_stats["n_ratings"] >= min_ratings]
    return eligible.nlargest(n, "mean_rating")


def main() -> None:
    st.set_page_config(page_title="MovieLens Dashboard", layout="wide")
    st.title("MovieLens Dashboard")
    st.caption("Four views of the MovieLens ratings file: genres, satisfaction, release years, and top movies.")

    ratings = load_ratings()
    unique_movies = ratings.drop_duplicates(subset=["movie_id"])
    n_movies = unique_movies["movie_id"].nunique()

    with st.sidebar:
        st.header("About")
        st.write(
            "This app reads `data/movie_ratings.csv` (one row per user rating) "
            "and answers four questions with Plotly charts."
        )
        st.metric("Ratings", f"{len(ratings):,}")
        st.metric("Movies rated", f"{n_movies:,}")

    # --- Q1 ---
    st.header("Question 1 — Genre breakdown")
    st.info(
        "**How multi-genre movies are counted:** the `genres` column is split on `|`. "
        "Each movie is counted once **per listed genre** (a film tagged Drama|Romance "
        "appears in both bars). Genre totals therefore **exceed** the number of unique "
        "movies. That is expected: we are not double-counting titles in the catalog; "
        "we are assigning a movie to every genre it belongs to. Counts below are of "
        "**unique movies that were rated**, not of rating rows."
    )

    movies_exploded = explode_genres(unique_movies)
    genre_counts = (
        movies_exploded.groupby("genre", as_index=False)["movie_id"]
        .nunique()
        .rename(columns={"movie_id": "n_movies"})
        .sort_values("n_movies", ascending=True)
    )
    genre_total = int(genre_counts["n_movies"].sum())
    top_genre = genre_counts.iloc[-1]

    st.write(
        f"Among **{n_movies:,}** rated movies, **{top_genre['genre']}** is the "
        f"most common genre ({int(top_genre['n_movies']):,} movies). Summing the "
        f"bars gives **{genre_total:,}** genre assignments (more than {n_movies:,} movies)."
    )

    fig_q1 = px.bar(
        genre_counts,
        x="n_movies",
        y="genre",
        orientation="h",
        labels={"n_movies": "Rated movies", "genre": "Genre"},
        title="Rated movies per genre (multi-label)",
    )
    fig_q1.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_q1, width="stretch")

    # --- Q2 ---
    st.header("Question 2 — Genre satisfaction")
    ratings_exploded = explode_genres(ratings)
    genre_means = (
        ratings_exploded.groupby("genre", as_index=False)
        .agg(mean_rating=("rating", "mean"), n_ratings=("rating", "size"))
        .sort_values("mean_rating", ascending=True)
    )
    highest = genre_means.iloc[-1]
    lowest = genre_means.iloc[0]

    st.write(
        "Each rating of a multi-genre movie is included in **every** one of that "
        "movie's genres, then we take the mean rating. "
        f"**{highest['genre']}** has the highest average "
        f"({highest['mean_rating']:.2f}); **{lowest['genre']}** has the lowest "
        f"({lowest['mean_rating']:.2f})."
    )

    fig_q2 = px.bar(
        genre_means,
        x="mean_rating",
        y="genre",
        orientation="h",
        hover_data={"n_ratings": ":,", "mean_rating": ":.3f"},
        labels={"mean_rating": "Average rating", "genre": "Genre"},
        title="Average rating by genre",
    )
    fig_q2.update_layout(xaxis_range=[genre_means["mean_rating"].min() - 0.15, 5])
    st.plotly_chart(fig_q2, width="stretch")

    # --- Q3 ---
    st.header("Question 3 — Ratings over time")
    by_year = (
        ratings.dropna(subset=["year"])
        .assign(year=lambda d: d["year"].astype(int))
        .groupby("year", as_index=False)
        .agg(mean_rating=("rating", "mean"), n_ratings=("rating", "size"))
        .sort_values("year")
    )
    peak = by_year.loc[by_year["mean_rating"].idxmax()]
    trough = by_year.loc[by_year["mean_rating"].idxmin()]

    st.write(
        "Mean rating is grouped by **movie release year** (`year`), not when the "
        "user rated it. Older titles in this set tend to sit higher: the peak year "
        f"is **{int(peak['year'])}** ({peak['mean_rating']:.2f}); the lowest is "
        f"**{int(trough['year'])}** ({trough['mean_rating']:.2f}). Hover a point "
        "to see how many ratings that year contributed — early years are sparse."
    )

    fig_q3 = px.line(
        by_year,
        x="year",
        y="mean_rating",
        markers=True,
        hover_data={"n_ratings": ":,", "mean_rating": ":.3f"},
        labels={"year": "Release year", "mean_rating": "Average rating"},
        title="Mean rating by movie release year",
    )
    fig_q3.update_yaxes(range=[by_year["mean_rating"].min() - 0.1, 5])
    st.plotly_chart(fig_q3, width="stretch")

    # --- Q4 ---
    st.header("Question 4 — Best movies, with a floor")
    movie_stats = ratings.groupby(["movie_id", "title"], as_index=False).agg(
        mean_rating=("rating", "mean"),
        n_ratings=("rating", "size"),
    )

    top50 = top_movies(movie_stats, 50)
    top150 = top_movies(movie_stats, 150)
    titles_50 = set(top50["title"])
    titles_150 = set(top150["title"])
    dropped = sorted(titles_50 - titles_150)
    added = sorted(titles_150 - titles_50)

    st.write(
        "A movie with one 5-star rating would otherwise dominate a leaderboard. "
        "We keep only titles with at least **N** ratings, then rank by mean rating."
    )
    st.write(
        "**Floor of 50:** "
        + "; ".join(
            f"{row.title} ({row.mean_rating:.2f}, n={int(row.n_ratings)})"
            for row in top50.itertuples()
        )
        + "."
    )
    st.write(
        "**Floor of 150:** "
        + "; ".join(
            f"{row.title} ({row.mean_rating:.2f}, n={int(row.n_ratings)})"
            for row in top150.itertuples()
        )
        + "."
    )
    if dropped or added:
        change_bits = []
        if dropped:
            change_bits.append("drop out: " + ", ".join(dropped))
        if added:
            change_bits.append("enter the top 5: " + ", ".join(added))
        st.write("Raising the floor from 50 to 150, these titles **" + "; ".join(change_bits) + "**.")
    else:
        st.write("The same five titles remain in the top 5 at both floors.")

    min_n = st.radio(
        "Minimum number of ratings",
        options=[50, 150],
        index=0,
        horizontal=True,
    )
    shown = top_movies(movie_stats, min_n).sort_values("mean_rating", ascending=True)

    fig_q4 = px.bar(
        shown,
        x="mean_rating",
        y="title",
        orientation="h",
        hover_data={"n_ratings": ":,", "mean_rating": ":.3f"},
        labels={"mean_rating": "Average rating", "title": "Movie"},
        title=f"Top 5 movies with at least {min_n} ratings",
    )
    fig_q4.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_q4, width="stretch")


if __name__ == "__main__":
    main()
