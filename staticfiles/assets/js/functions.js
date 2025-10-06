// const $ = (id) => document.getElementById(id);

// Preloader (safe)
// const preloader = $("preloader");
// if (preloader) {
//     window.addEventListener("load", () => {
//         setTimeout(() => preloader.classList.add("hidden"), 500);
//     });
// }

document.addEventListener("DOMContentLoaded", () => {
    const nav = $("main-nav");
    if (!nav) return;

    // read homepage flag set by template (true/false)
    const isHomepage = nav.dataset.homepage === "true";

    // Common elements (may be missing on some pages)
    const topBar = $("top-bar");
    const mainNavContent = $("main-nav-content");
    const bottomBar = $("bottom-bar");
    const hamburgerBtn = $("hamburger-btn");
    const sidebar = $("sidebar");
    const sidebarOverlay = $("sidebar-overlay");
    const closeSidebarBtn = $("close-sidebar-btn");
    const sidebarLinksContainer = $("sidebar-links");
    const desktopLinks = document.getElementById("desktop-links");
    const startShoppingBtn = $("start-shopping-btn");
    const allNavLinks = document.querySelectorAll("nav a");

    // hero & main content are only expected on homepage
    const videoHero = $("video-hero");
    const mainContent = $("main-content");

    // Safety: populate sidebar links by cloning desktop links (only if both exist)
    if (sidebarLinksContainer && desktopLinks) {
        const clone = desktopLinks.cloneNode(true);
        sidebarLinksContainer.innerHTML = clone.innerHTML;
    }

    // Sidebar open/close
    const openSidebar = () => {
        if (sidebar) sidebar.classList.remove("sidebar-hidden");
        if (sidebarOverlay) sidebarOverlay.classList.remove("hidden");
    };
    const closeSidebar = () => {
        if (sidebar) sidebar.classList.add("sidebar-hidden");
        if (sidebarOverlay) sidebarOverlay.classList.add("hidden");
    };
    if (hamburgerBtn) hamburgerBtn.addEventListener("click", openSidebar);
    if (closeSidebarBtn) closeSidebarBtn.addEventListener("click", closeSidebar);
    if (sidebarOverlay) sidebarOverlay.addEventListener("click", closeSidebar);

    // Modal safe listeners (if modal exists)
    const dealsModal = $("deals-modal");
    const modalOverlay = $("deals-modal-overlay");
    const closeModalBtn = $("close-modal-btn");
    const showModal = () => {
        if (dealsModal) dealsModal.classList.remove("modal-hidden");
        if (modalOverlay) modalOverlay.classList.remove("modal-hidden");
    };
    const hideModal = () => {
        if (dealsModal) dealsModal.classList.add("modal-hidden");
        if (modalOverlay) modalOverlay.classList.add("modal-hidden");
    };

    if (closeModalBtn) closeModalBtn.addEventListener("click", hideModal);
    if (modalOverlay) modalOverlay.addEventListener("click", hideModal);

    // Style helpers
    const applyScrolledNavStyles = () => {
        nav.style.backgroundColor = "#8C001A";
        nav.classList.add("shadow-lg");
    };
    const applyTransparentNavStyles = () => {
        nav.style.backgroundColor = "transparent";
        nav.classList.remove("shadow-lg");
    };
    const showAllNav = () => {
        if (window.innerWidth >= 768) {
            if (topBar) topBar.style.display = "flex";
            if (bottomBar) bottomBar.style.display = "flex";
        }
    };
    const hideNavParts = () => {
        if (window.innerWidth >= 768) {
            if (topBar) topBar.style.display = "none";
            if (bottomBar) bottomBar.style.display = "none";
        }
    };

    // fast smooth scroll
    const fastScrollTo = (target, duration = 400) => {
        const targetPosition = typeof target === "number" ? target : (target && target.offsetTop) || 0;
        const startPosition = window.pageYOffset;
        const distance = targetPosition - startPosition;
        let startTime = null;
        const animation = (currentTime) => {
            if (startTime === null) startTime = currentTime;
            const timeElapsed = currentTime - startTime;
            const run = Math.min(1, timeElapsed / duration);
            const easedProgress = run < 1 ? run * (2 - run) : 1;
            const newPosition = startPosition + distance * easedProgress;
            window.scrollTo(0, newPosition);
            if (timeElapsed < duration) requestAnimationFrame(animation);
        };
        requestAnimationFrame(animation);
    };

    // Nav links behaviour: scroll to main content (if present)
    const handleNavLinkClick = (e) => {
        // if link is external or has target, don't override
        if (e.currentTarget.target && e.currentTarget.target !== "") return;
        e.preventDefault();
        if (mainContent) fastScrollTo(mainContent, 500);
        closeSidebar();
    };
    // allNavLinks.forEach((link) => link.addEventListener("click", handleNavLinkClick));
    // if (sidebarLinksContainer) {
    //     sidebarLinksContainer.querySelectorAll("a").forEach((link) => link.addEventListener("click", handleNavLinkClick));
    // }
    if (startShoppingBtn) startShoppingBtn.addEventListener("click", () => fastScrollTo(mainContent, 500));

    // If this page is NOT homepage -> set minimized header by default and skip scroll-snap logic
    if (!isHomepage) {
        // set to scrolled/minimized header state
        applyScrolledNavStyles();
        hideNavParts();

        // keep expand-on-hover behavior
        nav.addEventListener("mouseenter", () => {
            nav.style.backgroundColor = "#800000";
            showAllNav();
        });
        nav.addEventListener("mouseleave", () => {
            nav.style.backgroundColor = "#8C001A";
            hideNavParts();
        });
        return; // done for non-home pages
    }

    // --- homepage-only behaviour starts here ---
    // Guards for hero / mainContent existence
    if (!videoHero || !mainContent) {
        // If hero/mainContent missing (unexpected), fallback to minimized header behavior
        applyTransparentNavStyles();
        showAllNav();
        return;
    }

    // snap behaviour variables
    let snapDownLock = false;
    let snapUpLock = false;
    let lastScrollY = window.scrollY || 0;

    window.addEventListener("scroll", () => {
        const currentScrollY = window.scrollY || 0;
        const scrollingDown = currentScrollY > lastScrollY;
        const scrollingUp = currentScrollY < lastScrollY;
        const heroHeight = Math.max(0, videoHero.offsetHeight || 0);

        // fade hero with scroll
        const fadeEnd = heroHeight * 0.8;
        const scrollPercentage = fadeEnd > 0 ? Math.min(1, currentScrollY / fadeEnd) : 1;
        videoHero.style.opacity = String(1 - scrollPercentage);

        // snap scroll (only on larger screens as before)
        if (window.innerWidth > 768) {
            if (scrollingDown && currentScrollY > 0 && currentScrollY < heroHeight / 2 && !snapDownLock) {
                snapDownLock = true;
                snapUpLock = false;
                fastScrollTo(mainContent, 500);
            }
            if (scrollingUp && currentScrollY < heroHeight - 10 && !snapUpLock) {
                snapUpLock = true;
                snapDownLock = false;
                fastScrollTo(0, 500);
            }
        }

        lastScrollY = currentScrollY <= 0 ? 0 : currentScrollY;

        // header minimize & show-on-hover
        if (window.scrollY > 50) {
            applyScrolledNavStyles();
            if (!nav.matches(":hover")) {
                hideNavParts();
            }
        } else {
            applyTransparentNavStyles();
            showAllNav();
        }
    });

    // hover behavior (homepage)
    nav.addEventListener("mouseenter", () => {
        if (window.scrollY > 50) {
            nav.style.backgroundColor = "#800000";
            showAllNav();
        }
    });
    nav.addEventListener("mouseleave", () => {
        if (window.scrollY > 50) {
            nav.style.backgroundColor = "#8C001A";
            hideNavParts();
        }
    });
    // --- end homepage-only behaviour ---
});

// glide/carousel init (safe)
if (document.querySelector(".glide")) {
    try {
        new Glide(".glide", {
            type: "carousel",
            startAt: 0,
            perView: 4,
            gap: 20,
            autoplay: 1500,
            hoverpause: true,
            breakpoints: {
                1024: { perView: 3 },
                768: { perView: 2 },
                640: { perView: 1 },
            },
        }).mount();
    } catch (err) {
        console.warn("Glide init failed:", err);
    }
}
