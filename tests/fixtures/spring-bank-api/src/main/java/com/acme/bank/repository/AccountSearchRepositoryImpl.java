package com.acme.bank.repository;

import com.acme.bank.model.Account;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.util.List;

public class AccountSearchRepositoryImpl implements AccountSearchRepository {

    @PersistenceContext
    private EntityManager em;

    @Override
    @SuppressWarnings("unchecked")
    public List<Account> searchByOwner(String owner) {
        return em.createNativeQuery("SELECT * FROM account WHERE owner LIKE '%" + owner + "%'", Account.class)
                .getResultList();
    }
}
