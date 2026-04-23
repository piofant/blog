---
layout: page
title: Все посты
permalink: /archive/
---

<div class="archive-page">
{% assign date_format = site.date_format | default: "%B %-d, %Y" %}
{% assign posts_by_year = site.posts | group_by_exp: "post", "post.date | date: '%Y'" %}
{% for year in posts_by_year %}
  <h2 class="archive-year">{{ year.name }}</h2>
  <ul class="archive-list">
    {% for post in year.items %}
    <li>
      <span class="d">{{ post.date | date: date_format }}</span>
      <a href="{{ post.url | relative_url }}">{{ post.title }}</a>
    </li>
    {% endfor %}
  </ul>
{% endfor %}
</div>
