# The page's structure, in the app and in the prototype

Written by `qa/walks/j2ui-e2e.sh` (shot-j2.js, kind `outline`). The outline lists, for each view, every element of the page's own markup as `tag#id.classes` (no text), indented by depth. Where the page fills an element with data (a pane, the chat, the progress strip) the element is followed by one `~` line: the distinct tags and classes found beneath it, so a difference in data (more messages, another card) is not a difference in structure. The page is the prototype's file at commit `f9ceba15192b`, changed only by the three documented substitutions (S1 relative paths, S2 one script line, S3 fonts), so its skeleton must be the prototype's own.

## Simple view (`#sview`)

- skeleton: **identical** (20 lines in the app, 20 in the prototype's page)
- classes and tags the page fills its panes with: 12 in the app, 9 in the prototype's page on its own saved run; 7 shared
- only in the app (data it was given): a, button#sask-change, div.acts, div.ready, h2
- only in the prototype's page (data its run had): li, ol

```text
div#sview
  header.shead
    b#stitle
    span#sotype.meta
    span.spacer
    a#to-detail.slink
  main.smain
    div.stoggle
      button
      button
    section.schat
      div#sprog.sprog
        ~ div, div.done, i
      div#smsgs.smsgs
        ~ a, button#sask-change, div.acts, div.me.sb, div.ready, div.sb.team, h2, p.sq, small
      div#sstatus.sstatus
      div.scompose
        div.row
          textarea#sbox
          button#ssend.send
    section.sprev
      iframe#sframe
```

## Detailed view (`#dview`: the rail, the work panes, the chat)

- skeleton: **identical** (76 lines in the app, 76 in the prototype's page)
- classes and tags the page fills its panes with: 152 in the app, 155 in the prototype's page on its own saved run; 138 shared
- only in the app (data it was given): b.ctype, details.atom, div.ablock, div.apreview, div.fold, div.foldbody, div.outcome, h4.agroup, span.aud.tag, span.checks.mappill, span.none, span.pass, text.mapcnt.sub, ul.clist
- only in the prototype's page (data its run had): div.W-1.msg, div.W-2.msg, div.W-3.msg, div.W-4.msg, div.W-5.msg, div.W-6.msg, div.audit.msg, div.coordination.msg, div.needitem, div.sys, h3.fail, img, path.branch.mapedge, span.bad.tag, span.fail, span.mappill.nochecks, td.fail

```text
div#dview
  nav.rail.tabs
    button
      svg
        circle
        circle
        circle
        path
      span
    button#gochat
      svg
        path
      span
    button#internals
      svg
        path
      span
    div#railsub.railsub
      button
      button
      button
      button
      button
      button
      button
      button
      button
      button#tab-board
      button
      button
      button
      button
      button
      button
  div.dcol
    section#needs.needs
      ~ button.linkbtn, div.outcome, h2, span.needbadge, span.none
    main
      section.mapfit.work
        div.wbar
          div
            button#backmap.linkbtn
            h2#wtitle.wtitle
            span#wsub.wsub
          select#ver
            ~ option
        div#pane-preview.pane.preview
          ~ divs.doclinks, iframe
        div#pane-goal.pane
          ~ br, dd, dl, dt, h3, span.done.pill
        div#pane-workflows.pane
          ~ a, b, b.ctype, br, button.linkbtn, button.otag, details, details.atom, div, div.ablock, div.apreview, div.bar, div.fold, div.foldbody, div.legend, div.ogroups, div.runsum, div.wtags, h3, h4, h4.agroup, i, li, p, p.empty, span, span.code, span.done.pill, span.empty, span.pass, summary, table, tbody, td, th, tr, ul.clist
        div#pane-conflicts.pane
          ~ p.empty
        div#pane-timeline.pane
          ~ b, br, button.chip, div.tline, h3, p.empty, span, span.empty, span.mark
        div#pane-audit.pane
          ~ b, h3, p.empty, span.pass, table, tbody, td, td.pass, th, tr
        div#pane-charter.pane
          ~ b, div.chused, div.docbody, h4, header.dochead, li.dl, ol.chitems, p.brief, p.chnote.empty, section.doc, span.code, span.docmeta
        div#pane-docs.pane
          ~ a, a.empty, b, div.docbody, div.docdiv, header.dochead, nav.docjump, p.empty, section.doc, span, span.code
        div#pane-artifacts.pane
          ~ b, button.linkbtn, div, div.artrow, h3, span.empty, span.otag
        div#pane-board.pane
        div#pane-map.pane
          ~ a, b, br, circle, circle.shape, circle.teamdot, circle.teamhit, circle.youdot, defs, details.mapdd, details.mapdd.mapleg, details.mapnr, div.mapcard.st-filed, div.mapcard.st-idle, div.mapcards, div.maphead, div.maplegend, div.mapstep, div.mapsvgwrap, div.mapwrap, div.sub, g.mapfn.mapnode, g.mapnode, h3, li, line, line.rowdiv, marker, path, path.mapedge, path.mapedge.speak, path.mapedge.trunk, path.mapln, polygon, polygon.shape, rect, rect.shape, span, span.checks.mappill, span.idle.mappill, summary, svg, svg.mapsvg, svg.mapsvg.mapvert, table.maptable, tbody, td, text, text.chipn.sub, text.mapcnt, text.mapcnt.sub, text.maplbl, text.rowlab, text.sub, th, thead, title, tr, tspan, ul
        div#pane-style.pane
          ~ p.empty
        div#pane-lessons.pane
          ~ p.empty
        div#pane-playbooks.pane
          ~ p.empty
        div#pane-report.pane
          ~ div, div.banner, p.empty
        div#pane-runsettings.pane
          ~ asimple.slink, buttonset.ghost, div.runact, div.runset, label, option, selectsel.ghost, selectsel.outsel
        div#pane-rundetails.pane
          ~ asides.lanes, b, br, button.lane, div#steps.steps, div.past.st, div.rdmeta, div.st, h2, small.code, span.d, span.lock, span.meta, span.pg, span.pill.st-idle, span.warn, spans.warn, spanstles.warn
      section.chat
        div#msgs.msgs
          ~ b, div, div.adaptation.msg, div.av, div.bubble, div.identity.msg, div.identity.msg.touser, div.msg.priority, div.msg.user, div.msg.validator, div.text, div.who, span, span.aud.tag, span.ok.tag, span.tag, span.touser-label
        div#typing.typing
        div.compose
          div#waiting.waiting
          div#quick.quick
            ~ button
          div.row
            textarea#box
            button#send.send
  dialog#detail
    div.dhead
      b#dtitle
      span.spacer
      button#dclose.ghost
    div#dbody.dbody
```
