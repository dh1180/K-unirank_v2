(function () {
    "use strict";

    function normalized(value) {
        return String(value || "")
            .normalize("NFKC")
            .toLocaleLowerCase("ko-KR")
            .replace(/\s+/g, "");
    }

    function init() {
        var input = document.getElementById("support-university-search");
        var select = document.getElementById("id_university");
        var status = document.getElementById("support-search-status");
        if (!input || !select || !status) return;

        var original = Array.from(select.options).map(function (option) {
            return { value: option.value, label: option.textContent };
        });
        var selectable = original.filter(function (option) { return option.value !== ""; });
        var placeholder = original.find(function (option) { return option.value === ""; }) ||
            { value: "", label: "대학교 선택" };

        function filterOptions() {
            var term = normalized(input.value);
            var currentlySelected = select.value;
            var matches = selectable.filter(function (option) {
                return !term || normalized(option.label).includes(term);
            });

            var newOptions = [placeholder].concat(matches).map(function (option) {
                return new Option(option.label, option.value);
            });
            select.replaceChildren.apply(select, newOptions);
            var present = matches.some(function (option) {
                return option.value === currentlySelected;
            });
            select.value = present ? currentlySelected : "";

            if (!term) {
                status.textContent = "가나다순 전체 " + selectable.length + "개 대학";
            } else if (matches.length === 0) {
                status.textContent = "검색 결과가 없습니다. 다른 이름으로 검색해보세요.";
            } else {
                status.textContent = matches.length + "개 대학 검색됨 · 아래 목록에서 선택하세요.";
            }
        }
        input.addEventListener("input", filterOptions);
        filterOptions();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
}());
