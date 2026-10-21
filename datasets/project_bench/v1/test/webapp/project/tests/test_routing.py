import pytest

from webapp.routing import Request, Response, Router, compile_template


def echo(request: Request) -> Response:
    return Response(200, {"params": dict(request.params)})


def test_placeholders_are_captured():
    router = Router()
    router.add("GET", "/users/<name>/posts/<post_id>", echo)
    response = router.dispatch(Request("GET", "/users/ana/posts/7"))
    assert response.status == 200
    assert response.body["params"] == {"name": "ana", "post_id": "7"}


def test_unknown_path_is_404():
    router = Router()
    router.add("GET", "/users/<name>", echo)
    assert router.dispatch(Request("GET", "/teams/x")).status == 404


def test_path_must_match_completely():
    router = Router()
    router.add("GET", "/users/<name>", echo)
    assert router.dispatch(Request("GET", "/users/ana/extra")).status == 404


def test_wrong_method_is_405_with_allow_header():
    router = Router()
    router.add("GET", "/items/<item_id>", echo)
    router.add("DELETE", "/items/<item_id>", echo)
    response = router.dispatch(Request("POST", "/items/3"))
    assert response.status == 405
    assert response.headers["Allow"] == "DELETE, GET"


def test_method_is_case_insensitive():
    router = Router()
    router.add("get", "/ping", echo)
    assert router.dispatch(Request("GET", "/ping")).status == 200


def test_duplicate_route_is_rejected():
    router = Router()
    router.add("GET", "/ping", echo)
    with pytest.raises(ValueError):
        router.add("GET", "/ping", echo)


def test_template_must_start_with_slash():
    with pytest.raises(ValueError):
        compile_template("users/<name>")


def test_header_lookup_ignores_case():
    request = Request("GET", "/", headers={"content-type": "application/json"})
    assert request.header("Content-Type") == "application/json"
    assert request.header("Accept") is None
