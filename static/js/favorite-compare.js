document.addEventListener('DOMContentLoaded', function () {
    const checkboxes = Array.from(document.querySelectorAll('.js-favorite-compare'));
    const submitButton = document.getElementById('favorite-compare-submit');
    const guide = document.getElementById('favorite-compare-guide');

    if (!checkboxes.length || !submitButton || !guide) return;

    function refresh() {
        const checked = checkboxes.filter((checkbox) => checkbox.checked);
        const count = checked.length;

        submitButton.disabled = count < 2;
        submitButton.textContent = count >= 2
            ? `선택한 대학 비교하기 (${count}/3)`
            : '선택한 대학 비교하기';

        if (count === 0) {
            guide.textContent = '2~3개 대학을 선택해주세요.';
        } else if (count === 1) {
            guide.textContent = '한 곳만 더 선택하면 비교할 수 있어요.';
        } else if (count === 2) {
            guide.textContent = '2개 대학을 비교합니다. 한 곳을 더 선택할 수도 있어요.';
        } else {
            guide.textContent = '최대 3개 대학을 선택했습니다.';
        }

        checkboxes.forEach((checkbox) => {
            checkbox.disabled = count >= 3 && !checkbox.checked;
            const card = checkbox.closest('.favorite-card');
            if (card) card.classList.toggle('compare-selected', checkbox.checked);
        });
    }

    checkboxes.forEach((checkbox) => {
        checkbox.addEventListener('change', refresh);
    });

    refresh();
});
