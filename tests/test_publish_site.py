from shop.tools.publish_site import _without_timestamp


def test_payload_comparison_ignores_only_the_timestamp():
    old = {"updated_at": "2026-11-07T10:00:00+00:00", "currency": "RUB", "items": [{"code": "A"}]}
    same_but_later = {**old, "updated_at": "2026-11-14T10:00:00+00:00"}
    with_videos = {**same_but_later, "community": {"title": "Video", "links": [{"title": "X", "url": "https://x.test"}]}}
    with_food_tab = {**same_but_later, "show_food_tab": True}

    assert _without_timestamp(old) == _without_timestamp(same_but_later)
    # A change to the video buttons or the food-tab setting alone must still republish.
    assert _without_timestamp(old) != _without_timestamp(with_videos)
    assert _without_timestamp(old) != _without_timestamp(with_food_tab)
