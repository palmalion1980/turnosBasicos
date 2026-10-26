const dialogo = document.getElementById('dialogo-nota');
if (dialogo) {
    document.querySelectorAll('.dia-celda[data-fecha]').forEach(celda => {
        celda.addEventListener('click', () => {
            const [a, m, d] = celda.dataset.fecha.split('-');
            document.getElementById('nota-titulo').textContent = `Nota del ${d}/${m}/${a}`;
            document.getElementById('nota-fecha').value = celda.dataset.fecha;
            document.getElementById('nota-texto').value = celda.dataset.nota;
            dialogo.showModal();
        });
    });
    document.getElementById('nota-cancelar').addEventListener('click', () => dialogo.close());
}

document.querySelectorAll('[data-confirmar]').forEach(btn => {
    btn.addEventListener('click', e => {
        if (!confirm(btn.dataset.confirmar)) e.preventDefault();
    });
});
