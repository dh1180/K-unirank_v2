from django.http import HttpResponsePermanentRedirect


PRIMARY_HOST = "k-unirank.com"
LEGACY_HOST = "www.k-unirank.com"


class CanonicalDomainMiddleware:
    """SEO 기준 도메인을 k-unirank.com 하나로 통일한다.

    www 요청이 애플리케이션까지 도달하면 루트 도메인으로 301 이동시키고,
    과거 템플릿/구조화 데이터에 남아 있는 www 절대 URL도 HTML 응답에서
    루트 도메인으로 정규화한다.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":", 1)[0].lower()
        if host == LEGACY_HOST:
            target = f"https://{PRIMARY_HOST}{request.get_full_path()}"
            return HttpResponsePermanentRedirect(target)

        response = self.get_response(request)

        content_type = response.get("Content-Type", "").lower()
        if "text/html" in content_type and not response.streaming:
            encoding = response.charset or "utf-8"
            html = response.content.decode(encoding)
            old = f"https://{LEGACY_HOST}"
            new = f"https://{PRIMARY_HOST}"
            if old in html:
                response.content = html.replace(old, new).encode(encoding)
                response["Content-Length"] = str(len(response.content))

        return response
