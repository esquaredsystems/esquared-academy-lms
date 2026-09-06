/*
 * Take the "App" step out of the breadcrumb, separator and all.
 *
 * Django writes the bar as
 *
 *     <a>Home</a> " › " <a href="/admin/app/">App</a> " › Lessons"
 *
 * — note the last separator and the page name share one text node. So
 * removing the link and then hunting for a stray separator after it does
 * not work: the survivor is welded to the title and reads "Home > >
 * Lessons". The separator that belongs to a step is the one *before* it,
 * so that is the one that goes.
 *
 * Done here rather than by overriding change_list.html, change_form.html,
 * delete_confirmation.html and the rest, which would mean forking JET's
 * templates — the thing base_site.html asks us not to do.
 */
(function () {
  "use strict";

  var ONLY_SEPARATOR = /^\s*[>›»\/|·-]+\s*$/;
  var LEADING_SEPARATOR = /^\s*[>›»\/|·-]+\s*/;

  function isBlank(node) {
    return node.nodeType === Node.TEXT_NODE && !node.nodeValue.trim();
  }

  function isSeparator(node) { return isSeparatorOnly(node); }

  function isSeparatorOnly(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      return ONLY_SEPARATOR.test(node.nodeValue);
    }
    if (node.nodeType !== Node.ELEMENT_NODE) { return false; }
    if (node.tagName === "A" || node.querySelector("a")) { return false; }
    return ONLY_SEPARATOR.test(node.textContent);
  }

  function previousMeaningful(node) {
    var prev = node.previousSibling;
    while (prev && isBlank(prev)) { prev = prev.previousSibling; }
    return prev;
  }

  function nextMeaningful(node) {
    var next = node.nextSibling;
    while (next && isBlank(next)) { next = next.nextSibling; }
    return next;
  }

  function removeStep(step) {
    var before = previousMeaningful(step);
    var after = nextMeaningful(step);

    if (before && isSeparatorOnly(before)) {
      before.parentNode.removeChild(before);       // the usual case
    } else if (after && isSeparatorOnly(after)) {
      after.parentNode.removeChild(after);         // it was the first step
    } else if (after && after.nodeType === Node.TEXT_NODE &&
               LEADING_SEPARATOR.test(after.nodeValue)) {
      // The separator is welded to the next crumb's text: " › Lessons".
      after.nodeValue = after.nodeValue.replace(LEADING_SEPARATOR, "");
    }
    step.parentNode.removeChild(step);
  }

  function tidy(bar) {
    Array.prototype.forEach.call(
      bar.querySelectorAll('a[href$="/admin/app/"]'),
      function (link) {
        // If the link sits in a wrapper of its own, take the wrapper.
        var step = link;
        if (link.parentNode !== bar && link.parentNode.children.length === 1) {
          step = link.parentNode;
        }
        removeStep(step);
      }
    );

    // A final sweep: no two separators in a row, anywhere. Belt and
    // braces — the markup varies between Django's page templates and
    // JET's, and this holds whatever shape it takes.
    var nodes = Array.prototype.slice.call(bar.childNodes);
    var lastWasSeparator = false;
    nodes.forEach(function (node) {
      if (isBlank(node)) { return; }
      if (isSeparator(node)) {
        if (lastWasSeparator) {
          node.parentNode.removeChild(node);
          return;
        }
        lastWasSeparator = true;
        return;
      }
      if (lastWasSeparator && node.nodeType === Node.TEXT_NODE &&
          LEADING_SEPARATOR.test(node.nodeValue)) {
        node.nodeValue = node.nodeValue.replace(LEADING_SEPARATOR, "");
      }
      lastWasSeparator = false;
    });

    // Whatever is left must not start with a separator.
    var first = bar.firstChild;
    while (first && isBlank(first)) { first = first.nextSibling; }
    if (first && isSeparatorOnly(first)) {
      first.parentNode.removeChild(first);
    } else if (first && first.nodeType === Node.TEXT_NODE) {
      first.nodeValue = first.nodeValue.replace(LEADING_SEPARATOR, "");
    }
  }

  function run() {
    Array.prototype.forEach.call(
      document.querySelectorAll(".breadcrumbs, .breadcrumb, ul.breadcrumbs"),
      tidy
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
