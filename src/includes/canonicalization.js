const canonicalizeThreadTitle = title => {
    const normalized = String(title || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/\s+/g, ' ')
        .trim();
    const lower = normalized.toLowerCase();
    const aliases = [
        [/^taina(?:ná)? costa$/i, 'Taina Costa'],
        [/^s(?:z|sz)a(?:\s*-\s*solana rowe)?$/i, 'SZA'],
        [/^c(?:l|é)o pires$/i, 'Cleo Pires'],
        [/^cinthia cruz(?:\s+@[\w.-]+)?$/i, 'Cinthia Cruz'],
        [/^breckie hill(?:\s*\([^)]*\))?$/i, 'Breckie Hill'],
        [/^(?:rebeca|beca) barreto$/i, 'Beca Barreto'],
        [/^halle bailey(?:\s+actress)?(?:\s*\([^)]*\))?$/i, 'Halle Bailey'],
        [/^georgina rodr(?:í|i)guez$/i, 'Georgina Rodriguez'],
        [/^rubi rose$/i, 'Rubi Rose'],
        [/^yesjulz|julieanna marie goddard$/i, 'YesJulz'],
        [/^mikaela (?:la)?fuente|mikalafuente$/i, 'Mikaela Lafuente'],
        [/^gabriela moura$/i, 'Gabriela Moura'],
        [/^beyonc(?:é|e)(?: knowles)?$/i, 'Beyoncé'],
        [/^mari gonzalez|mari baianinha$/i, 'Mari Gonzalez'],
        [/^(?:mariely e mirella|g(?:ê|e)meas lacração)$/i, 'Gêmeas Lacração'],
        [/^mel maia|melissa mel maia$/i, 'Mel Maia'],
        [/^khloe kardashian$/i, 'Khloe Kardashian'],
        [/^caro(?:l|lina) portaluppi$/i, 'Carolina Portaluppi'],
        [/^vivi wanderley$/i, 'Vivi Wanderley'],
        [/^iza(?:\s+cantora)?$/i, 'IZA'],
        [/^tracee ellis ross$/i, 'Tracee Ellis Ross'],
        [/^laauura.*model$/i, 'Laauura'],
        [/^doechii/i, 'Doechii'],
        [/^fernanda lacerda|mendigata$/i, 'Fernanda Lacerda'],
        [/^carol dias|panicat$/i, 'Carol Dias'],
        [/^flay|flayslane$/i, 'Flay'],
        [/^(?:gwen stacy|spider[- ]?gwen)$/i, 'Gwen Stacy'],
        [/^val(?:es)?ca popozuda$/i, 'Valesca Popozuda'],
        [/^barbie ferreira/i, 'Barbie Ferreira'],
        [/^andressa soares|mulher melancia$/i, 'Andressa Soares'],
        [/^rafa kalimann$/i, 'Rafa Kalimann'],
        [/^gillian anderson/i, 'Gillian Anderson'],
        [/^aline mineiro/i, 'Aline Mineiro'],
        [/^karoline lima$/i, 'Karoline Lima'],
        [/^anya taylor[- ]joy$/i, 'Anya Taylor Joy'],
        [/^nicole.*coco.*austin$/i, 'Nicole Coco Austin'],
        [/^ice spice$/i, 'Ice Spice'],
        [/^anastasia karanikolaou|stassiebaby$/i, 'Anastasia Karanikolaou'],
        [/^ellen rocche$/i, 'Ellen Rocche'],
        [/^fl(?:á|a)via alessandra$/i, 'Flavia Alessandra'],
        [/^cinna(?:brit)?$/i, 'Cinnabrit'],
        [/^bianca andrade|boca rosa$/i, 'Bianca Andrade'],
        [/^ana paula minerato|apminerato$/i, 'Ana Paula Minerato'],
        [/^lu(?:í|i)sa sonza$/i, 'Luisa Sonza'],
        [/^rosal(?:í|i)a?(?:\s*la\s*rosal(?:í|i)a)?$/i, 'Rosalia'],
        [/^aryna sabalenka|arina sobolenko$/i, 'Aryna Sabalenka'],
        [/^dina belenkaya|thebelenkaya$/i, 'Dina Belenkaya'],
        [/^priscila evellyn$/i, 'Priscila Evellyn'],
        [/^b(?:á|a)rbara labres$/i, 'Barbara Labres'],
        [/^alessandra espanha$/i, 'Alessandra Espanha'],
        [/^juliana salimeni$/i, 'Juliana Salimeni'],
        [/^ad(?:è|e)le exarchopoulos$/i, 'Adèle Exarchopoulos'],
        [/^maraisa$/i, 'Maraisa'],
        [/^beabadoobee|beatrice laus$/i, 'Beabadoobee'],
        [/^alicia keys$/i, 'Alicia Keys'],
        [/^rhea ripley|wwe rhea ripley$/i, 'Rhea Ripley'],
        [/^jordyn woods$/i, 'Jordyn Woods'],
        [/^winona ryder$/i, 'Winona Ryder'],
        [/^lindsay capuano$/i, 'Lindsay Capuano'],
        [/^agatha s(?:á|a)$/i, 'Agatha Sá'],
        [/^lara juc(?:á|a)$/i, 'Lara Jucá'],
        [/^anna estrella$/i, 'Anna Estrella'],
        [/^ludmilla$/i, 'Ludmilla'],
    ];

    const alias = aliases.find(([pattern]) => pattern.test(normalized));
    if (alias) return alias[1];

    return normalized
        .replace(/\s+@[a-z0-9_.-]+$/i, '')
        .replace(/\s*\([^)]*\)\s*$/g, '')
        .replace(/\s*\[[^\]]*\]\s*$/g, '')
        .trim() || lower;
};
