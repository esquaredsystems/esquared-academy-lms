(function () {
    "use strict";

    function setupSidebarSections() {
        var sections = document.querySelectorAll(".sidebar-section");

        sections.forEach(function (section, index) {
            var title = section.querySelector(":scope > .sidebar-title");
            if (!title || section.classList.contains("last")) {
                return;
            }

            var content = Array.from(section.children).filter(function (child) {
                return child !== title;
            });
            if (!content.length) {
                return;
            }

            var key = "academy-sidebar-section-" + index;
            var toggle = document.createElement("button");
            toggle.type = "button";
            toggle.className = "sidebar-section-toggle";
            toggle.setAttribute("aria-label", "Expand or collapse section");
            toggle.setAttribute("aria-expanded", "true");
            title.insertBefore(toggle, title.firstChild);

            var storedState = window.localStorage.getItem(key);
            var hasCurrentLink = Array.from(section.querySelectorAll("a")).some(function (link) {
                return link.href === window.location.href;
            });
            var collapsed = storedState === "collapsed" && !hasCurrentLink;

            function setCollapsed(value) {
                section.classList.toggle("sidebar-section-collapsed", value);
                toggle.setAttribute("aria-expanded", String(!value));
                window.localStorage.setItem(key, value ? "collapsed" : "expanded");
            }

            toggle.addEventListener("click", function () {
                setCollapsed(!section.classList.contains("sidebar-section-collapsed"));
            });
            setCollapsed(collapsed);
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", setupSidebarSections);
    } else {
        setupSidebarSections();
    }
})();
