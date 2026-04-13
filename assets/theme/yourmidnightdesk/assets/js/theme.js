(function () {
    function onReady(callback) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", callback);
        } else {
            callback();
        }
    }

    function initDrawer() {
        var drawer = document.querySelector("[data-mobile-drawer]");
        var openButton = document.querySelector("[data-drawer-open]");
        var closeButton = document.querySelector("[data-drawer-close]");

        if (!drawer || !openButton || !closeButton) {
            return;
        }

        function setOpen(isOpen) {
            drawer.classList.toggle("is-open", isOpen);
            document.body.classList.toggle("drawer-open", isOpen);
            openButton.setAttribute("aria-expanded", isOpen ? "true" : "false");
        }

        openButton.addEventListener("click", function () {
            setOpen(true);
        });

        closeButton.addEventListener("click", function () {
            setOpen(false);
        });

        drawer.addEventListener("click", function (event) {
            if (event.target === drawer) {
                setOpen(false);
            }
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && drawer.classList.contains("is-open")) {
                setOpen(false);
            }
        });
    }

    function initDrawerGroups() {
        document.querySelectorAll("[data-drawer-group]").forEach(function (group) {
            var toggle = group.querySelector("[data-drawer-toggle]");
            if (!toggle) {
                return;
            }

            toggle.addEventListener("click", function () {
                var isOpen = group.classList.toggle("is-open");
                toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
            });
        });
    }

    function initRecipeFeed() {
        var root = document.querySelector("[data-recipe-feed]");
        if (!root || !window.ymdTheme || !window.ymdTheme.ajaxUrl) {
            return;
        }

        var grid = root.querySelector("[data-recipe-grid]");
        var loadMoreButton = root.querySelector("[data-load-more]");
        var chipButtons = Array.prototype.slice.call(root.querySelectorAll("[data-feed-filter]"));
        var page = parseInt(root.getAttribute("data-page") || "1", 10);
        var activeFilter = root.getAttribute("data-active-filter") || "all";
        var isLoading = false;

        if (!grid) {
            return;
        }

        function setLoading(state) {
            isLoading = state;
            root.classList.toggle("is-loading", state);
            if (loadMoreButton) {
                loadMoreButton.disabled = state;
                loadMoreButton.textContent = state
                    ? window.ymdTheme.loadingLabel
                    : window.ymdTheme.loadMoreLabel;
            }
        }

        function setActiveChip(slug) {
            activeFilter = slug;
            root.setAttribute("data-active-filter", slug);
            chipButtons.forEach(function (button) {
                var isActive = button.getAttribute("data-feed-filter") === slug;
                button.classList.toggle("is-active", isActive);
                button.setAttribute("aria-pressed", isActive ? "true" : "false");
            });
        }

        function toggleLoadMore(hasMore) {
            if (!loadMoreButton) {
                return;
            }
            loadMoreButton.hidden = !hasMore;
        }

        function requestFeed(reset) {
            if (isLoading) {
                return;
            }

            setLoading(true);

            var payload = new URLSearchParams();
            payload.append("action", "ymd_recipe_feed");
            payload.append("nonce", window.ymdTheme.nonce);
            payload.append("page", String(page));
            payload.append("filter", activeFilter);

            fetch(window.ymdTheme.ajaxUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
                },
                body: payload.toString()
            })
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error("Request failed");
                    }
                    return response.json();
                })
                .then(function (response) {
                    if (!response || !response.success || !response.data) {
                        throw new Error("Invalid payload");
                    }

                    if (reset) {
                        grid.innerHTML = response.data.html;
                    } else {
                        grid.insertAdjacentHTML("beforeend", response.data.html);
                    }

                    toggleLoadMore(!!response.data.has_more);
                })
                .catch(function () {
                    if (loadMoreButton) {
                        loadMoreButton.hidden = true;
                    }
                })
                .finally(function () {
                    setLoading(false);
                });
        }

        chipButtons.forEach(function (button) {
            button.addEventListener("click", function () {
                var nextFilter = button.getAttribute("data-feed-filter") || "all";
                if (nextFilter === activeFilter) {
                    return;
                }
                page = 1;
                setActiveChip(nextFilter);
                requestFeed(true);
            });
        });

        if (loadMoreButton) {
            loadMoreButton.addEventListener("click", function () {
                if (isLoading) {
                    return;
                }
                page += 1;
                root.setAttribute("data-page", String(page));
                requestFeed(false);
            });
        }
    }

    onReady(function () {
        initDrawer();
        initDrawerGroups();
        initRecipeFeed();
    });
})();
