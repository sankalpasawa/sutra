Sutra-owned (scripts/port_j2_ui.py never writes this folder).

fonts/: the two type faces of the studio look, served from this origin so the app works offline (the page CSP allows no outside font).
  figtree.woff2               Figtree, variable weight, Latin subset, from the npm package @fontsource-variable/figtree@5.1.1
                              (files/figtree-latin-wght-normal.woff2), sha256 93a68eaa293304b947a167d0f7d0e00a1a8b5cf4972dc0da3da2094359a33e9a
  bricolage-grotesque.woff2   Bricolage Grotesque, variable weight, Latin subset, from @fontsource-variable/bricolage-grotesque@5.1.1
                              (files/bricolage-grotesque-latin-wght-normal.woff2), sha256 639cc4132fdda71f490d52c862b3d3ac8ed3da2f89969c96fecd8bb22e99a095
  Licence: SIL Open Font License 1.1, see fonts/OFL-*.txt. Used by sutra-front.css and project_rail.css (Home, the project sidebar, the welcome card).
