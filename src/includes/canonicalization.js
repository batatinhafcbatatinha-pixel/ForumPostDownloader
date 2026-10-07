const canonicalizeThreadTitle = title => {
    const normalized = String(title || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/\s+/g, ' ')
        .trim();
    const lower = normalized.toLowerCase();
    const aliases = [
        [/^cyberpunk 2077|world of cyberpunk 2077$/i, 'Cyberpunk 2077'],
        [/^georgina rodriguez$/i, 'Georgina Rodriguez'],
        [/^taina costa$/i, 'Taina Costa'],
        [/^sza(?:\s*-\s*solana rowe)?$/i, 'SZA'],
        [/^cleo pires$/i, 'Cleo Pires'],
        [/^cinthia cruz(?:\s+@[\w.-]+)?$/i, 'Cinthia Cruz'],
        [/^breckie hill(?:\s*\([^)]*\))?$/i, 'Breckie Hill'],
        [/^(?:rebeca|beca) barreto$/i, 'Beca Barreto'],
        [/^halle bailey(?:\s+actress)?(?:\s*\([^)]*\))?$/i, 'Halle Bailey'],
        [/^rubi rose|rubixrose$/i, 'Rubi Rose'],
        [/^yesjulz|julieanna marie goddard$/i, 'YesJulz'],
        [/^mikaela (?:lafuente|fuente)|mika lafuente|mikalafuente$/i, 'Mikaela Lafuente'],
        [/^gabriela moura|gabimfmoura$/i, 'Gabriela Moura'],
        [/^beyonce(?: knowles)?$/i, 'Beyonce'],
        [/^mari gonzalez|mari baianinha$/i, 'Mari Gonzalez'],
        [/^mariely e mirella|gemeas lacracao$/i, 'Mariely e Mirella Santos'],
        [/^mel maia|melissa mel maia$/i, 'Mel Maia'],
        [/^khloe kardashian$/i, 'Khloe Kardashian'],
        [/^carolina portaluppi|carol portaluppi$/i, 'Carolina Portaluppi'],
        [/^mayaguod16|maya goudeseune$/i, 'MayaGuod16'],
        [/^vivi wanderley$/i, 'Vivi Wanderley'],
        [/^iza(?: cantora)?$/i, 'IZA'],
        [/^tracee ellis ross$/i, 'Tracee Ellis Ross'],
        [/^laauura(?:model| model)?|laauura_1$/i, 'Laauura'],
        [/^doechii(?: tde artist)?$/i, 'Doechii'],
        [/^fernanda lacerda|mendigata$/i, 'Fernanda Lacerda'],
        [/^carol dias|panicat$/i, 'Carol Dias'],
        [/^flay|flayslane bbb20$/i, 'Flay'],
        [/^gwen stacy|spider[- ]gwen$/i, 'Gwen Stacy'],
        [/^valeska popozuda|valesca popozuda$/i, 'Valeska Popozuda'],
        [/^barbie ferreira$/i, 'Barbie Ferreira'],
        [/^andressa soares|mulher melancia$/i, 'Andressa Soares'],
        [/^priscila evellyn$/i, 'Priscila Evellyn'],
        [/^barbara labres$/i, 'Barbara Labres'],
        [/^rafa kalimann$/i, 'Rafa Kalimann'],
        [/^gillian anderson$/i, 'Gillian Anderson'],
        [/^aline mineiro$/i, 'Aline Mineiro'],
        [/^stellar blade$/i, 'Stellar Blade'],
        [/^street fighter$/i, 'Street Fighter'],
        [/^karoline lima$/i, 'Karoline Lima'],
        [/^metal gear solid|quiet$/i, 'Metal Gear Solid'],
        [/^dreamworks animation|fiona from shrek$/i, 'Dreamworks Animation'],
        [/^lara croft|tomb raider$/i, 'Lara Croft'],
        [/^dc rule34|dc comics$/i, 'DC Rule34'],
        [/^naruto animations - aniflow|naruto(?: \/ boruto)?$/i, 'Naruto'],
        [/^anya taylor[- ]joy$/i, 'Anya Taylor Joy'],
        [/^nicole .*coco.*austin$/i, 'Nicole Coco Austin'],
        [/^ice spice$/i, 'Ice Spice'],
        [/^anastasia karanikolaou|stassiebaby$/i, 'Anastasia Karanikolaou'],
        [/^ellen rocche$/i, 'Ellen Rocche'],
        [/^flavia alessandra$/i, 'Flavia Alessandra'],
        [/^cinna(?:brit)?$/i, 'Cinna'],
        [/^bianca andrade|boca rosa$/i, 'Bianca Andrade'],
        [/^ana paula minerato|apminerato$/i, 'Ana Paula Minerato'],
        [/^luisa sonza$/i, 'Luisa Sonza'],
        [/^rosalia|la rosalia$/i, 'Rosalia'],
        [/^aryna sabalenka|arina sobolenko$/i, 'Aryna Sabalenka'],
        [/^dina belenkaya|thebelenkaya$/i, 'Dina Belenkaya'],
        [/^familia sacana|familia sacana e outros$/i, 'Familia sacana animacoes'],
        [/^alessandra espanha|alessandraespanha$/i, 'Alessandra Espanha'],
        [/^juliana salimeni$/i, 'Juliana Salimeni'],
        [/^adele exarchopoulos$/i, 'Adele Exarchopoulos'],
        [/^maraisa$/i, 'Maraisa'],
        [/^beabadoobee|beatrice laus$/i, 'Beabadoobee'],
        [/^alicia keys$/i, 'Alicia Keys'],
        [/^rhea ripley|wwe rhea ripley$/i, 'Rhea Ripley'],
        [/^jordyn woods$/i, 'Jordyn Woods'],
        [/^one piece$/i, 'One Piece'],
        [/^winona ryder$/i, 'Winona Ryder'],
        [/^lindsay capuano$/i, 'Lindsay Capuano'],
        [/^agatha sa$/i, 'Agatha Sa'],
        [/^rick and morty - pleasure trip [12]$/i, 'Rick and Morty - Pleasure Trip 2'],
        [/^dragon ball(?: z)?$/i, 'Dragon Ball'],
        [/^india love (?:& crystal westbrooks|westbrooks)$/i, 'India Love & Crystal Westbrooks'],
        [/^lara juca$/i, 'Lara Juca'],
        [/^anna estrella$/i, 'Anna Estrella'],
        [/^ludmilla(?: cantora)?$/i, 'Ludmilla'],
        [/^nier automata$/i, 'NieR:Automata'],
    ];

    const alias = aliases.find(([pattern]) => pattern.test(normalized));
    if (alias) return alias[1];

    return normalized
        .replace(/\s+@[a-z0-9_.-]+$/i, '')
        .replace(/\s*\([^)]*\)\s*$/g, '')
        .replace(/\s*\[[^\]]*\]\s*$/g, '')
        .trim() || lower;
};