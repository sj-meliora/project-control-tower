/* Project Control Tower 대시보드.
   집계 스크립트가 만든 data/status.json을 읽어서 화면을 그린다. 화면 구성은 DESIGN.md의 DP-5를 따른다.
   data/status.json이 없으면 예시 데이터(example/status.json)를 표시한다.
   집계 결과에서 온 값은 모두 textContent로만 넣는다. */
(function () {
  'use strict';

  var DATA_URL = 'data/status.json';
  var EXAMPLE_URL = 'example/status.json';
  var STALE_HOURS = 48;
  // 약칭 아이콘의 색. 프로젝트 이름에 따라 하나를 고르며, 색에는 의미가 없다.
  var TONES = ['#3f5fc4', '#1f7a6d', '#7a4bb3', '#a8651f', '#55657a', '#b03a68'];

  var view = document.getElementById('view');
  var meta = document.getElementById('meta');
  var notice = document.getElementById('notice');
  var data = null;
  var filter = null;
  var stageName = {};

  function h(tag, attrs, kids) {
    var el = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v == null || v === false) return;
        if (k === 'text') el.textContent = String(v);
        else if (k === 'on') Object.keys(v).forEach(function (e) { el.addEventListener(e, v[e]); });
        else el.setAttribute(k, v === true ? '' : String(v));
      });
    }
    (kids || []).forEach(function (c) { if (c) el.appendChild(c); });
    return el;
  }

  function list(x) { return Array.isArray(x) ? x : []; }
  function pad(n) { return String(n).padStart(2, '0'); }

  function mono(name) {
    var parts = String(name).split(/[-_.\s]+/).filter(Boolean);
    var m = parts.length > 1 ? parts.map(function (p) { return p[0]; }).join('') : String(name).slice(0, 2);
    return m.slice(0, 3).toUpperCase();
  }
  function tone(name) {
    var x = 5381;
    for (var i = 0; i < name.length; i++) x = ((x * 33) ^ name.charCodeAt(i)) >>> 0;
    return TONES[x % TONES.length];
  }
  function key(p) { return 'p-' + [p.host, p.owner, p.name].join('-').toLowerCase().replace(/[^a-z0-9]+/g, '-'); }
  function current(p) {
    var open = list(p.roadmap).filter(function (m) { return m.state === 'open'; });
    return open.length ? open[0] : null;
  }
  function pct(m) { var t = m.open + m.closed; return t ? Math.round(m.closed / t * 100) : 0; }
  function fmt(iso) {
    var d = new Date(iso);
    if (isNaN(d)) return '알 수 없음';
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }
  function ago(iso) {
    var t = Date.parse(iso);
    if (isNaN(t)) return '알 수 없음';
    var n = Math.max(0, Math.floor((Date.parse(data.aggregatedAt) - t) / 864e5));
    return n === 0 ? '오늘' : n < 60 ? n + '일 전' : Math.floor(n / 30) + '개월 전';
  }
  // 엠블럼은 이 사이트 안의 상대 경로만 허용한다.
  function iconSrc(p) {
    var src = p.icon;
    return typeof src === 'string' && /^[A-Za-z0-9._\/-]+$/.test(src) && src.indexOf('..') < 0 && src[0] !== '/' ? src : null;
  }
  function iconEl(p) {
    var src = iconSrc(p);
    if (src) return h('div', { class: 'icon emblem', 'aria-hidden': 'true' }, [h('img', { src: src, alt: '' })]);
    return h('div', { class: 'icon', style: '--tone:' + tone(p.name), 'aria-hidden': 'true', text: mono(p.name) });
  }
  function chips(p) {
    return h('div', { class: 'chips' }, list(p.stages).map(function (id) {
      return h('span', { class: 'chip' + (filter === id ? ' hit' : ''), text: stageName[id] || id });
    }));
  }
  function bar(m) {
    var i = document.createElement('i');
    i.style.width = pct(m) + '%';
    return h('div', { class: 'bar', role: 'img', 'aria-label': '진행률 ' + pct(m) + '%' }, [i]);
  }
  function find() {
    var id = decodeURIComponent((location.hash || '').slice(1));
    return data.projects.filter(function (p) { return key(p) === id; })[0] || null;
  }
  function go(p) {
    if (p) location.hash = key(p);
    else {
      try { history.replaceState(null, '', location.pathname + location.search); } catch (e) { location.hash = ''; }
      render();
    }
    window.scrollTo(0, 0);
  }

  function render() {
    view.textContent = '';
    var p = find();
    if (p) detail(p); else home();
  }

  function home() {
    var withIssues = data.projects.filter(function (p) { return p.openIssues > 0; }).length;
    meta.textContent = '집계 ' + fmt(data.aggregatedAt) + ' · 열린 이슈가 있는 프로젝트 ' + withIssues + '개';
    var shown = data.projects.filter(function (p) { return !filter || list(p.stages).indexOf(filter) >= 0; });

    var stepper = h('nav', { class: 'stepper', 'aria-label': '개발 워크플로', style: '--n:' + data.stages.length }, data.stages.map(function (s, i) {
      var n = data.projects.filter(function (p) { return list(p.stages).indexOf(s.id) >= 0; }).length;
      return h('button', { type: 'button', class: 'node', 'aria-pressed': filter === s.id ? 'true' : 'false', on: { click: function () { filter = filter === s.id ? null : s.id; render(); } } }, [
        h('span', { class: 'circle', text: String(i + 1) }),
        h('span', { class: 'nm', text: s.name }),
        h('span', { class: 'ct num' }, [h('span', { class: 'lbl', text: '프로젝트 ' }), document.createTextNode(n + '개')])
      ]);
    }));

    var grid = shown.length ? h('div', { class: 'grid' }, shown.map(card))
      : h('div', { class: 'state' }, [h('strong', { text: filter ? '이 단계에 등록된 프로젝트가 없어요' : '등록된 프로젝트가 없어요' }),
          document.createTextNode('프로젝트는 목록 파일에 항목을 추가하는 PR로 등록해요.')]);

    view.appendChild(h('div', { style: 'display:flex;flex-direction:column;gap:24px' }, [
      stepper,
      h('section', { style: 'display:flex;flex-direction:column;gap:20px' }, [
        h('div', { class: 'listhead' }, [
          h('h2', { text: (filter ? (stageName[filter] || filter) + ' 단계의 프로젝트' : '전체 프로젝트') + ' ' + shown.length + '개' }),
          filter ? h('button', { type: 'button', class: 'reset', text: '전체 보기', on: { click: function () { filter = null; render(); } } }) : null
        ]),
        grid
      ])
    ]));
  }

  function card(p) {
    var m = current(p), sub;
    if (p.error) {
      sub = [h('span', { class: 'failed', text: '집계하지 못했어요' }), chips(p)];
    } else {
      sub = [
        h('span', { class: 'issues num' + (p.openIssues > 0 ? ' on' : ''), text: p.openIssues > 0 ? '열린 이슈 ' + p.openIssues + '건' : '열린 이슈 없음' }),
        m ? h('span', { class: 'ms' }, [h('span', { class: 'row' }, [h('span', { class: 'ttl', text: m.title }), h('span', { class: 'num', text: pct(m) + '%' })]), bar(m)])
          : h('span', { text: '로드맵 없음' }),
        chips(p)
      ];
    }
    return h('button', { type: 'button', class: 'tile', 'aria-label': p.name + ' 열기', on: { click: function () { go(p); } } }, [
      iconEl(p),
      h('span', { class: 'tbody' }, [h('span', { class: 'name', text: p.name }), h('span', { class: 'sub' }, sub)])
    ]);
  }

  function detail(p) {
    meta.textContent = '집계 ' + fmt(data.aggregatedAt);
    var m = current(p);
    var left = h('div', { class: 'col' }), right = h('div', { class: 'col' });

    if (p.error) {
      left.appendChild(h('section', { class: 'sec' }, [h('h3', { text: '집계' }),
        h('div', { class: 'signal on' }, [h('span', { class: 'big', text: '집계하지 못했어요' }), h('span', { class: 'd', text: p.error })])]));
    } else {
      left.appendChild(h('section', { class: 'sec' }, [h('h3', { text: '이슈' }),
        h('div', { class: 'signal' + (p.openIssues > 0 ? ' on' : '') }, [
          h('span', { class: 'big num', text: p.openIssues > 0 ? '열린 이슈 ' + p.openIssues + '건' : '열린 이슈 없음' }),
          h('span', { class: 'd', text: p.openIssues > 0 ? '처리할 일이 있어요. 내용은 GitHub의 Issues에서 확인해요.' : '지금 등록된 처리할 일이 없어요.' })])]));
      left.appendChild(h('section', { class: 'sec' }, [h('h3', { text: '로드맵' }),
        list(p.roadmap).length ? h('ol', { class: 'road' }, p.roadmap.map(function (x) {
          var isNow = x === m, cls = x.state === 'closed' ? 'closed' : (isNow ? 'now' : '');
          var t = h('span', { class: 't', text: x.title });
          if (isNow) t.appendChild(h('span', { class: 'tag', text: '현재 위치' }));
          var line = x.state === 'closed' ? '완료' : (x.dueOn ? '마감 ' + x.dueOn : '마감일 없음') + ' · 이슈 ' + x.closed + '/' + (x.open + x.closed) + ' 완료';
          return h('li', { class: cls }, [h('span', { class: 'dot' }), h('span', { class: 'body' }, [t, h('span', { class: 'd num', text: line }), isNow ? bar(x) : null])]);
        })) : h('p', { class: 'empty', text: '마일스톤이 없어서 로드맵을 표시하지 않아요.' })]));
    }

    right.appendChild(h('section', { class: 'sec' }, [h('h3', { text: '관련 워크플로 단계' }), chips(p)]));
    var base = typeof p.url === 'string' && p.url.indexOf('https://') === 0 ? p.url : null;
    if (base) {
      right.appendChild(h('section', { class: 'sec' }, [h('h3', { text: 'GitHub에서 보기' }), h('div', { class: 'links' },
        [['저장소', '첫 화면', base], ['Issues', '처리할 일', base + '/issues'], ['Milestones', '로드맵', base + '/milestones'], ['Wiki', '문서', base + '/wiki']].map(function (l) {
          var a = h('a', { href: l[2], target: '_blank', rel: 'noopener', text: l[0] });
          a.appendChild(h('span', { text: l[1] }));
          return a;
        }))]));
    }

    var facts = [h('span', { text: p.host + '/' + p.owner })];
    if (p.pushedAt) facts.push(h('span', { text: '마지막 푸시 ' + ago(p.pushedAt) }));
    if (p.archived) facts.push(h('span', { text: '보관된 저장소' }));

    view.appendChild(h('div', { style: 'display:flex;flex-direction:column;gap:26px' }, [
      h('button', { type: 'button', class: 'back', text: '← 전체 프로젝트', on: { click: function () { go(null); } } }),
      h('div', { class: 'head' }, [iconEl(p), h('div', { class: 'txt' }, [
        h('h2', { text: p.name }),
        p.description ? h('p', { class: 'desc', text: p.description }) : null,
        h('div', { class: 'facts' }, facts)])]),
      h('div', { class: 'cols' }, [left, right])
    ]));
  }

  function say(text, warn) {
    notice.textContent = text;
    notice.className = 'banner' + (warn ? ' warn' : '');
    notice.hidden = !text;
  }
  function fail(title, body) {
    meta.textContent = '';
    view.textContent = '';
    view.appendChild(h('div', { class: 'state' }, [h('strong', { text: title }), document.createTextNode(body)]));
  }
  function valid(d) {
    return d && typeof d === 'object' && Array.isArray(d.stages) && Array.isArray(d.projects);
  }
  function load(url) {
    return fetch(url, { cache: 'no-store' }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (d) {
      if (!valid(d)) throw new Error('형식이 올바르지 않음');
      return d;
    });
  }
  function start(d, example) {
    data = d;
    data.stages.forEach(function (s) { stageName[s.id] = s.name; });
    var hours = (Date.now() - Date.parse(data.aggregatedAt)) / 36e5;
    if (example) say('예시 데이터를 표시하고 있어요. 집계 결과 파일(' + DATA_URL + ')이 아직 없어요.', false);
    else if (hours > STALE_HOURS) say('마지막 집계가 ' + Math.floor(hours / 24) + '일 전이에요. 집계 워크플로가 실행되고 있는지 확인이 필요해요.', true);
    else say('', false);
    window.addEventListener('hashchange', render);
    render();
  }

  load(DATA_URL).then(function (d) { start(d, false); }, function () {
    return load(EXAMPLE_URL).then(function (d) { start(d, true); }, function () {
      fail('집계 결과를 불러오지 못했어요',
        location.protocol === 'file:' ? '파일을 직접 열면 데이터를 읽을 수 없어요. 저장소 폴더에서 python -m http.server를 실행한 뒤 http://localhost:8000 으로 열어 주세요.'
                                      : DATA_URL + ' 파일이 있는지, 형식이 올바른지 확인해 주세요.');
    });
  });
})();
