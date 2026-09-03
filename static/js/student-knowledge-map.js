/*
 * The student's knowledge map.
 *
 * The same tree the subject knowledge graph draws, rooted on the student
 * instead of on one subject, with each subject marked: a tick for passed,
 * a question mark for a subject being studied now, a cross for one never
 * taken. Topics hang under their subject and inherit its state, because
 * the schema has no per-topic result to show yet.
 *
 * Draws into #skm-canvas inside the Knowledge map tab of the student page.
 * JET builds its tabs after the page loads and keeps hidden tabs in the
 * document, so the tree can be laid out straight away — nodeSize means the
 * layout never depends on the container being visible.
 */
(function () {
  'use strict';

  var MARKS = {
    passed:    { glyph: '✓', colour: '#2f7d5b' },
    studying:  { glyph: '?',      colour: '#b07d18' },
    not_taken: { glyph: '✗', colour: '#a8a29a' }
  };

  var NODE_HEIGHT = 26;
  var LEVEL_WIDTH = 300;
  var MARGIN = { top: 26, right: 40, bottom: 26, left: 34 };

  function ready(fn) {
    if (document.readyState !== 'loading') { fn(); }
    else { document.addEventListener('DOMContentLoaded', fn); }
  }

  ready(function () {
    var panel = document.getElementById('skm');
    if (!panel || typeof d3 === 'undefined') { return; }

    var canvas = document.getElementById('skm-canvas');
    var meta = document.getElementById('skm-meta');
    var hideUntaken = document.getElementById('skm-hide-untaken');

    var payload = null;
    var root = null;
    var svg = null;
    var group = null;
    var counter = 0;

    function label(text) {
      text = text || '';
      return text.length > 48 ? text.slice(0, 45).replace(/\s+$/, '') + '...' : text;
    }

    function statusOf(node) {
      // Subjects and topics both carry their own mark now; the student at
      // the root does not.
      return node.data.status || null;
    }

    function suffix(node) {
      var data = node.data;
      if (data.type === 'subject') {
        return data.topics ? '  ' + data.percent + '%' : '';
      }
      if (data.leaves > 1) {
        return '  ' + data.passed_leaves + '/' + data.leaves;
      }
      return '';
    }

    function build() {
      var subjects = payload.subjects.filter(function (subject) {
        return !(hideUntaken.checked && subject.status === 'not_taken');
      });

      var tree = {
        name: payload.student.name,
        type: 'student',
        children: subjects.map(function (subject) {
          // A fresh object each time, so folding state is rebuilt cleanly
          // when the filter changes.
          return {
            id: subject.id,
            name: subject.name,
            short_name: subject.short_name,
            type: 'subject',
            status: subject.status,
            status_label: subject.status_label,
            percent: subject.percent,
            passed: subject.passed,
            assessed: subject.assessed,
            topics: subject.topics,
            children: subject.children
          };
        })
      };

      root = d3.hierarchy(tree, function (d) { return d.children; });
      root.each(function (d) {
        d.data.key = 'n' + (counter++);
        // Topics start folded: the interesting thing at a glance is which
        // subjects carry which mark, not 600 topic names.
        if (d.depth >= 1 && d.children) { d._children = d.children; d.children = null; }
      });
      draw();
    }

    function toggle(node) {
      if (node.children) { node._children = node.children; node.children = null; }
      else { node.children = node._children; node._children = null; }
      draw();
    }

    function setAll(node, open) {
      if (open && node._children) { node.children = node._children; node._children = null; }
      if (!open && node.children && node.depth > 0) {
        node._children = node.children; node.children = null;
      }
      (node.children || node._children || []).forEach(function (child) {
        setAll(child, open);
      });
    }

    function draw() {
      var laid = d3.tree().nodeSize([NODE_HEIGHT, LEVEL_WIDTH])(root);
      var nodes = laid.descendants();
      var links = laid.links();

      var minX = d3.min(nodes, function (d) { return d.x; });
      var maxX = d3.max(nodes, function (d) { return d.x; });
      var maxY = d3.max(nodes, function (d) { return d.y; });

      svg
        .attr('width', maxY + LEVEL_WIDTH + MARGIN.left + MARGIN.right)
        .attr('height', (maxX - minX) + MARGIN.top + MARGIN.bottom + NODE_HEIGHT);
      group.attr('transform',
        'translate(' + MARGIN.left + ',' + (MARGIN.top - minX) + ')');

      var link = group.selectAll('path.skm-link')
        .data(links, function (d) { return d.target.data.key; });
      link.enter().append('path').attr('class', 'skm-link')
        .merge(link)
        .attr('d', d3.linkHorizontal()
          .x(function (d) { return d.y; })
          .y(function (d) { return d.x; }));
      link.exit().remove();

      var node = group.selectAll('g.skm-node')
        .data(nodes, function (d) { return d.data.key; });

      var entered = node.enter().append('g')
        .attr('class', 'skm-node')
        .on('click', function (event, d) {
          if (d.children || d._children) { toggle(d); }
        });
      entered.append('circle').attr('r', 5);
      entered.append('text').attr('class', 'skm-mark-glyph').attr('dy', '0.32em');
      entered.append('text').attr('class', 'skm-name').attr('dy', '0.32em');

      var merged = entered.merge(node);

      merged
        .attr('transform', function (d) { return 'translate(' + d.y + ',' + d.x + ')'; })
        .attr('class', function (d) {
          return 'skm-node is-' + d.data.type
            + ' is-' + (statusOf(d) || 'root')
            + (d._children ? ' has-hidden' : '');
        });

      merged.select('circle').attr('fill', function (d) {
        var status = statusOf(d);
        return status ? MARKS[status].colour : '#8c491a';
      });

      merged.select('text.skm-mark-glyph')
        .attr('x', 12)
        .text(function (d) {
          var status = statusOf(d);
          return status ? MARKS[status].glyph : '';
        });

      merged.select('text.skm-name')
        .attr('x', function (d) { return d.data.type === 'student' ? 12 : 28; })
        .text(function (d) {
          var name = label(d.data.name) + suffix(d);
          return d._children ? name + '  +' + d._children.length : name;
        });

      merged.select('text.skm-name').select('title').remove();
      merged.select('text.skm-name').append('title').text(function (d) {
        var data = d.data;
        if (data.type === 'subject') {
          return data.name + ' — ' + data.status_label
            + (data.topics
                ? ' · ' + data.passed + ' of ' + data.topics + ' topics passed ('
                  + data.percent + '%), ' + data.assessed + ' assessed'
                : '');
        }
        if (data.type === 'topic' && data.leaves > 1) {
          return data.name + ' — ' + data.passed_leaves + ' of ' + data.leaves
            + ' topics under it passed';
        }
        return data.name;
      });

      node.exit().remove();

      var counts = payload.counts || {};
      var taken = payload.subjects.filter(function (subject) {
        return subject.status !== 'not_taken' && subject.topics;
      });
      var overall = taken.length
        ? Math.round(taken.reduce(function (sum, subject) {
            return sum + subject.percent;
          }, 0) / taken.length)
        : 0;

      meta.textContent =
        (counts.passed || 0) + ' passed · ' +
        (counts.studying || 0) + ' studying · ' +
        (counts.not_taken || 0) + ' never taken · ' +
        overall + '% of the topics taken · ' + payload.year;
    }

    function render() {
      canvas.innerHTML = '';
      if (!payload.subjects.length) {
        canvas.innerHTML = '<div class="skm-status">There are no subjects in the catalogue yet.</div>';
        return;
      }
      svg = d3.select(canvas).append('svg');
      group = svg.append('g');
      build();
    }

    fetch(panel.getAttribute('data-url') + '?year=' + panel.getAttribute('data-year'), {
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json' }
    })
      .then(function (response) {
        if (!response.ok) { throw new Error('HTTP ' + response.status); }
        return response.json();
      })
      .then(function (data) { payload = data; render(); })
      .catch(function (error) {
        canvas.innerHTML = '<div class="skm-status">Could not load the map: '
          + error.message + '</div>';
      });

    hideUntaken.addEventListener('change', function () {
      if (payload) { render(); }
    });
    document.getElementById('skm-expand').addEventListener('click', function () {
      if (root) { setAll(root, true); draw(); }
    });
    document.getElementById('skm-collapse').addEventListener('click', function () {
      if (root) { setAll(root, false); draw(); }
    });
  });
})();
