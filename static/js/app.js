document.querySelectorAll('table[data-sortable]').forEach(table => {
  table.querySelectorAll('th').forEach((header, index) => {
    if (!header.textContent.trim()) return;
    header.tabIndex = 0; header.title = 'Sort by ' + header.textContent;
    const sort = () => {
      const direction = header.dataset.direction === 'asc' ? -1 : 1;
      header.dataset.direction = direction === 1 ? 'asc' : 'desc';
      const body = table.tBodies[0];
      const rows = [...body.rows].filter(row => row.cells.length === table.tHead.rows[0].cells.length);
      rows.sort((a,b) => {
        const av = a.cells[index].textContent.trim(), bv = b.cells[index].textContent.trim();
        const an = Number(av.replace(/[$,%]/g,'')), bn = Number(bv.replace(/[$,%]/g,''));
        return direction * (av && bv && Number.isFinite(an) && Number.isFinite(bn) ? an-bn : av.localeCompare(bv, undefined, {numeric:true}));
      });
      rows.forEach(row => body.appendChild(row));
    };
    header.addEventListener('click',sort);
    header.addEventListener('keydown',e => {if(e.key==='Enter'||e.key===' ') {e.preventDefault();sort();}});
  });
});
