// Presentation-only behaviour.

// Ask for confirmation before a destructive submit.
document.addEventListener('submit', function (event) {
    var message = event.target.getAttribute('data-confirm');
    if (message && !window.confirm(message)) {
        event.preventDefault();
    }
});

// Header account menu (avatar + dropdown).
(function () {
    var menu = document.querySelector('[data-user-menu]');
    if (!menu) {
        return;
    }

    var trigger = menu.querySelector('[data-user-menu-trigger]');
    var panel = menu.querySelector('[data-user-menu-panel]');

    function close() {
        panel.hidden = true;
        trigger.setAttribute('aria-expanded', 'false');
    }

    function open() {
        panel.hidden = false;
        trigger.setAttribute('aria-expanded', 'true');
    }

    trigger.addEventListener('click', function (event) {
        event.stopPropagation();
        if (panel.hidden) {
            open();
        } else {
            close();
        }
    });

    document.addEventListener('click', function (event) {
        if (!menu.contains(event.target)) {
            close();
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            close();
        }
    });
})();

// Interactive cards: navigate on click.
document.addEventListener('click', function (event) {
    var card = event.target.closest('.card--interactive');
    if (card && card.dataset.href && !event.target.closest('a, button')) {
        window.location.href = card.dataset.href;
    }
});
